from __future__ import annotations

import base64
import hashlib
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import config as config_mod
from . import gemini, i18n, message, profile, scoring
from .i18n import t
from .db import STATUSES, Database
from .models import Job
from .refresh import run_refresh

STATIC = Path(__file__).parent / "static"
# The names JobRadar answers to. A site whose domain is pointed at 127.0.0.1 (DNS rebinding)
# arrives with its own name in the Host header and is turned away.
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]


class JobUpdate(BaseModel):
    status: str | None = None
    notes: str | None = None


class NewJob(BaseModel):
    """A job found where JobRadar can't look (e.g. LinkedIn), added by hand."""

    title: str = Field(min_length=1, max_length=200)
    company: str = Field("", max_length=200)
    url: str = Field("", max_length=2000)
    location: str = Field("", max_length=200)
    notes: str = Field("", max_length=5000)

    @field_validator("title", "company", "url", "location", mode="before")
    @classmethod
    def _strip(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("url")
    @classmethod
    def _http_only(cls, value: str) -> str:
        # it ends up in an href: a javascript: or data: link would run when clicked
        if value and not value.lower().startswith(("http://", "https://")):
            raise ValueError(t("o link tem de começar por http:// ou https://"))
        return value


class ConfigBody(BaseModel):
    yaml: str


class LanguageBody(BaseModel):
    language: str


class KeysBody(BaseModel):
    """Keys typed in the welcome screen; an empty field keeps the key already in .env."""

    ITJOBS_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""

    @field_validator("*", mode="before")
    @classmethod
    def _plain(cls, value):
        value = value.strip() if isinstance(value, str) else value
        # each becomes one KEY=value line in .env: a space, quote or newline would break it
        if value and not re.fullmatch(r"[A-Za-z0-9_.\-]{8,300}", value):
            raise ValueError(t("a chave só pode ter letras, números, '-', '_' e '.'"))
        return value


MAX_CV_BYTES = 5 * 1024 * 1024
SHORT, LONG = 300, 5000


class ProfileBody(BaseModel):
    """The 👤 Profile screen (see profile.py for where each field goes in config.yaml)."""

    name: str = Field("", max_length=SHORT)
    signature: str = Field("", max_length=SHORT)
    summary: str = Field("", max_length=LONG)
    facts: str = Field("", max_length=LONG)
    skills: list[str] = Field(default_factory=list, max_length=200)
    focus: list[str] = Field(default_factory=list, max_length=200)
    education: list[str] = Field(default_factory=list, max_length=50)
    projects: list[str] = Field(default_factory=list, max_length=50)
    experience: list[str] = Field(default_factory=list, max_length=50)
    positions: list[str] = Field(default_factory=list, max_length=200)
    locations: list[str] = Field(default_factory=list, max_length=50)  # empty: config.validate says so
    allow_remote: bool = False
    junior_only: bool = True

    @field_validator("skills", "focus", "education", "projects", "experience", "positions", "locations")
    @classmethod
    def _short_items(cls, items: list[str]) -> list[str]:
        if any(len(item) > SHORT for item in items):
            raise ValueError(t("cada item pode ter até {n} caracteres", n=SHORT))
        return items


class CvBody(BaseModel):
    pdf: str = Field(max_length=MAX_CV_BYTES * 4 // 3 + 4)  # base64 of a PDF of up to 5 MB


def key_status() -> dict[str, bool]:
    """Which keys are set: never their values."""
    return {key: bool(os.environ.get(key)) for key in config_mod.KEYS}


def create_app(
    config_path: Path | str = config_mod.DEFAULT_CONFIG,
    db_path: Path | str = "jobradar.db",
    refresh_kwargs: dict | None = None,
    llm_client=None,
    env_path: Path | str = ".env",
    allowed_hosts: list[str] | None = None,
) -> FastAPI:
    app = FastAPI(title="JobRadar")
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts or ALLOWED_HOSTS)

    @app.middleware("http")
    async def same_site_only(request: Request, call_next):
        # Browsers send Origin with every request from another site that changes something:
        # such a page must not start a search, spend the AI quota or change the keys.
        origin = request.headers.get("origin")
        if request.method not in ("GET", "HEAD") and origin and urlsplit(origin).netloc != request.headers.get("host"):
            return JSONResponse({"detail": t("Pedido recusado: vem de outro site.")}, status_code=403)
        return await call_next(request)

    db = Database(db_path)
    refresh_lock = threading.Lock()
    refresh_kwargs = refresh_kwargs or {}

    @app.get("/api/jobs")
    def list_jobs():
        return db.all_jobs()

    @app.post("/api/jobs", status_code=201)
    def add_job(body: NewJob):
        # same link, same job: adding it twice updates it instead of duplicating it
        key = body.url or uuid.uuid4().hex
        job = Job(source="manual", external_id=hashlib.sha1(key.encode()).hexdigest()[:12],
                  company=body.company, title=body.title, location=body.location, url=body.url)
        try:
            kw, reasons = scoring.keyword_score(job, config_mod.load(config_path))
        except config_mod.ConfigError:
            kw, reasons = 0, []
        new = db.upsert(job, kw, reasons, {}, datetime.now(timezone.utc).isoformat(timespec="seconds"))
        return db.update(job.uid, status="guardada" if new else None, notes=body.notes or None)

    def with_ai(call):
        """Runs an AI helper with the config, once the config is valid and the provider's key is set."""
        try:
            cfg = config_mod.load(config_path)
        except config_mod.ConfigError as exc:
            raise HTTPException(400, t("Configuração inválida: {error}", error=exc)) from exc
        key_env = scoring.llm_settings(cfg)["key_env"]
        if not os.environ.get(key_env):
            where = "aistudio.google.com" if key_env == "GEMINI_API_KEY" else "console.anthropic.com"
            raise HTTPException(400, t("Falta {key} no .env (cria a chave em {where}).", key=key_env, where=where))
        import anthropic

        try:
            return call(cfg)
        except (message.MessageError, gemini.GeminiError) as exc:
            raise HTTPException(502, str(exc)) from exc
        except anthropic.AuthenticationError as exc:
            raise HTTPException(400, t("A ANTHROPIC_API_KEY foi recusada. Confirma a chave no .env.")) from exc
        except anthropic.RateLimitError as exc:
            raise HTTPException(429, t("Demasiados pedidos à API da Anthropic. Tenta daqui a um minuto.")) from exc
        except anthropic.APIStatusError as exc:
            raise HTTPException(502, t("A API da Anthropic respondeu com o erro {code}.", code=exc.status_code)) from exc
        except anthropic.APIConnectionError as exc:
            raise HTTPException(502, t("Sem ligação à API da Anthropic.")) from exc

    def ai_text(uid: str, generate) -> dict:
        """Runs one of the AI helpers (message.write or message.interview) for a job."""
        job = db.get(uid)
        if job is None:
            raise HTTPException(404, t("Vaga não encontrada"))
        return {"text": with_ai(lambda cfg: generate(job, cfg, llm_client))}

    @app.get("/api/profile")
    def get_profile():
        try:
            cfg = config_mod.load(config_path)
        except config_mod.ConfigError as exc:
            raise HTTPException(400, t("Configuração inválida: {error}", error=exc)) from exc
        settings = scoring.llm_settings(cfg)
        # who reads the CV, shown on the screen before it is sent; "" = no AI key, fill it in by hand
        ai = {"gemini": "Gemini (Google)", "anthropic": "Claude (Anthropic)"}[settings["provider"]]
        return {"profile": profile.from_config(cfg), "example": profile.is_example(cfg),
                "ai": ai if os.environ.get(settings["key_env"]) else ""}

    @app.put("/api/profile")
    def put_profile(body: ProfileBody):
        try:
            cfg = config_mod.load(config_path)
            config_mod.update(profile.changes(profile.clean(body.model_dump()), cfg), config_path)
        except config_mod.ConfigError as exc:
            raise HTTPException(400, str(exc)) from exc
        return get_profile()

    @app.post("/api/profile/cv")
    def read_cv(body: CvBody):
        try:
            pdf = base64.b64decode(body.pdf, validate=True)
        except ValueError as exc:
            raise HTTPException(400, t("O ficheiro não é um PDF.")) from exc
        if not pdf.startswith(b"%PDF"):
            raise HTTPException(400, t("O ficheiro não é um PDF."))
        if len(pdf) > MAX_CV_BYTES:
            raise HTTPException(413, t("O CV tem mais de 5 MB."))
        # read only: the screen shows what the AI found and the person decides what to save
        return {"profile": with_ai(lambda cfg: profile.read_cv(pdf, cfg, llm_client))}

    @app.post("/api/jobs/{uid:path}/message")
    def job_message(uid: str):
        return ai_text(uid, message.write)

    @app.post("/api/jobs/{uid:path}/interview")
    def job_interview(uid: str):
        return ai_text(uid, message.interview)

    @app.patch("/api/jobs/{uid:path}")
    def update_job(uid: str, body: JobUpdate):
        if body.status is not None and body.status not in STATUSES:
            raise HTTPException(400, t("Estado inválido. Usa: {options}", options=", ".join(STATUSES)))
        job = db.update(uid, status=body.status, notes=body.notes)
        if job is None:
            raise HTTPException(404, t("Vaga não encontrada"))
        return job

    @app.post("/api/refresh")
    def refresh():
        if not refresh_lock.acquire(blocking=False):
            raise HTTPException(409, t("Já há uma atualização a correr."))
        try:
            cfg = config_mod.load(config_path)
            return {"runs": run_refresh(cfg, db, **refresh_kwargs)}
        except config_mod.ConfigError as exc:
            raise HTTPException(400, t("Configuração inválida: {error}", error=exc)) from exc
        finally:
            refresh_lock.release()

    @app.get("/api/runs")
    def runs():
        return db.last_runs()

    @app.get("/api/config")
    def get_config():
        return {"yaml": config_mod.read_text(config_path), "keys": key_status()}

    @app.get("/api/keys")
    def get_keys():
        return key_status()

    # Only JobRadar's own page can set the keys: other sites are stopped by same_site_only
    # and TrustedHostMiddleware, and a PUT from them also needs a CORS preflight this app never allows.
    @app.put("/api/keys")
    def put_keys(body: KeysBody):
        config_mod.save_keys({k: v for k, v in body.model_dump().items() if v}, env_path)
        return key_status()

    @app.put("/api/config")
    def put_config(body: ConfigBody):
        try:
            config_mod.save_text(body.yaml, config_path)
        except config_mod.ConfigError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"ok": True}

    @app.get("/api/language")
    def get_language():
        try:
            config_mod.load(config_path)  # config.yaml may have been edited by hand
        except (OSError, config_mod.ConfigError):
            pass
        return {"language": i18n.language}

    @app.put("/api/language")
    def put_language(body: LanguageBody):
        if body.language not in i18n.LANGUAGES:
            raise HTTPException(400, t("language tem de ser {options}.", options=" / ".join(i18n.LANGUAGES)))
        try:
            config_mod.set_language(body.language, config_path)
        except config_mod.ConfigError as exc:
            raise HTTPException(400, t("Configuração inválida: {error}", error=exc)) from exc
        return {"language": i18n.language}

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    app.state.db = db
    return app
