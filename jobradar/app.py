from __future__ import annotations

import base64
import csv
import hashlib
import hmac
import io
import logging
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import config as config_mod
from . import discover, gemini, i18n, link, message, profile, salary, scoring, skills
from .i18n import t
from .db import STATUSES, Database
from .filters import reason_label
from .models import Job
from .text import normalize
from .refresh import run_refresh, score_new
from .sources import make_client, source_label

STATIC = Path(__file__).parent / "static"
# The names JobRadar answers to. A site whose domain is pointed at 127.0.0.1 (DNS rebinding)
# arrives with its own name in the Host header and is turned away.
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
TOKEN_COOKIE = "jobradar"


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
    # filled in by "Read from the link"
    description: str = Field("", max_length=20000)
    posted_at: str = Field("", pattern=r"^(\d{4}-\d{2}-\d{2})?$")

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


class LinkBody(BaseModel):
    url: str = Field(min_length=1, max_length=2000)

    @field_validator("url")
    @classmethod
    def _http_only(cls, value: str) -> str:
        value = value.strip()
        if not value.lower().startswith(("http://", "https://")):
            raise ValueError(t("o link tem de começar por http:// ou https://"))
        return value


def _salary(job: dict) -> dict | None:
    return salary.find(" ".join([job.get("title") or "", job.get("contract") or "", job.get("description") or ""]))


def _cell(value) -> str:
    """A spreadsheet cell: text that starts like a formula (=, +, -, @, or a tab or return before one) could run
    in Excel, so it gets a quote in front and stays text."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


class ConfigBody(BaseModel):
    yaml: str


class LanguageBody(BaseModel):
    language: str


class FilterBody(BaseModel):
    """✂ Cut: the change that would have kept a job ("stop cutting titles with lead", "add Lousado to the area")."""

    action: Literal["remove", "add"]
    field: Literal["exclude_title_keywords", "exclude_keywords", "title_keywords", "locations"]
    word: str = Field(min_length=1, max_length=60)

    @field_validator("word")
    @classmethod
    def _one_line(cls, value: str) -> str:
        value = value.strip().lower()
        if not value or any(c in value for c in "\r\n"):
            raise ValueError(t("entrada inválida"))
        return value


class AiBody(BaseModel):
    choice: str = Field(min_length=1, max_length=100)  # "gemini:<model>" or "anthropic"


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


class CompanyBody(BaseModel):
    company: str = Field(min_length=1, max_length=200)


class SourceBody(BaseModel):
    """A company to follow, as discover.entry() made it: a platform and a few short fields."""

    kind: str
    entry: dict[str, str]

    @field_validator("entry")
    @classmethod
    def _plain(cls, entry: dict[str, str]) -> dict[str, str]:
        allowed = {"company", "name", "site", "country"}
        if not entry or set(entry) - allowed or any(not v.strip() or len(v) > 200 or "\n" in v for v in entry.values()):
            raise ValueError(t("entrada inválida"))
        return {k: v.strip() for k, v in entry.items()}


class CvBody(BaseModel):
    pdf: str = Field(max_length=MAX_CV_BYTES * 4 // 3 + 4)  # base64 of a PDF of up to 5 MB


def _same(given: str | None, token: str) -> bool:
    return hmac.compare_digest((given or "").encode(), token.encode())  # in constant time


def _claude_error(exc: Exception) -> None:
    """The Anthropic API's errors as messages for the page. Imported only with Claude: the phone app
    carries Gemini only, and importing anthropic there broke every AI button (error 500)."""
    import anthropic

    if isinstance(exc, anthropic.AuthenticationError):
        raise HTTPException(400, t("A ANTHROPIC_API_KEY foi recusada. Confirma a chave no .env.")) from exc
    if isinstance(exc, anthropic.RateLimitError):
        raise HTTPException(429, t("Demasiados pedidos à API da Anthropic. Tenta daqui a um minuto.")) from exc
    if isinstance(exc, anthropic.APIStatusError):
        raise HTTPException(502, t("A API da Anthropic respondeu com o erro {code}.", code=exc.status_code)) from exc
    if isinstance(exc, anthropic.APIConnectionError):
        raise HTTPException(502, t("Sem ligação à API da Anthropic.")) from exc


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
    token: str | None = None,
) -> FastAPI:
    """token: on the phone (android/main.py), where any other app can reach 127.0.0.1. The API then
    answers only the app's own window, which opened /?k=<token> once and got the cookie."""
    app = FastAPI(title="JobRadar")
    app.state.opened = threading.Event()  # someone opened the page: the phone's loading screen is done
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts or ALLOWED_HOSTS)

    @app.middleware("http")
    async def same_site_only(request: Request, call_next):
        # Browsers send Origin with every request from another site that changes something:
        # such a page must not start a search, spend the AI quota or change the keys.
        origin = request.headers.get("origin")
        if request.method not in ("GET", "HEAD") and origin and urlsplit(origin).netloc != request.headers.get("host"):
            return JSONResponse({"detail": t("Pedido recusado: vem de outro site.")}, status_code=403)
        if token and request.url.path.startswith("/api/") and not _same(request.cookies.get(TOKEN_COOKIE), token):
            return JSONResponse({"detail": t("Pedido recusado: vem de outra app.")}, status_code=403)
        response = await call_next(request)
        if request.url.path == "/" or request.url.path.startswith("/static/"):
            # ask again each time (a 304 when nothing changed): after an update, not last version's page
            response.headers.setdefault("Cache-Control", "no-cache")
        return response

    db = Database(db_path)
    refresh_lock = threading.Lock()
    scoring_lock = threading.Lock()
    app.state.scorer = None  # the thread scoring the new jobs with the AI, after a search (tests wait on it)
    app.state.progress = {"sources": [], "done": []}  # the search under way (refresh.run_refresh's on_progress)
    refresh_kwargs = refresh_kwargs or {}

    def score_later(cfg: dict) -> None:
        """The AI scores the new jobs after the search answers, one at a time as before: the list
        shows them at once with their keyword score, and the AI's score comes in afterwards."""
        if not scoring_lock.acquire(blocking=False):
            return  # it is already scoring; the rest are scored after the next search

        def work():
            try:
                score_new(cfg, db, refresh_kwargs.get("llm_client"))
            except Exception:  # never let the AI break the app
                logging.getLogger("jobradar").exception("A avaliação da IA falhou")
            finally:
                scoring_lock.release()

        app.state.scorer = threading.Thread(target=work, daemon=True)
        app.state.scorer.start()

    @app.get("/api/jobs")
    def list_jobs():
        jobs = db.all_jobs()
        for job in jobs:
            job["salary"] = _salary(job)
        return jobs

    @app.get("/api/cut")
    def cut_jobs():
        """The jobs the filters cut in the last search, and why (the ✂ tab)."""
        cut = db.cut_jobs()
        for job in cut:
            kind, _, word = job["reason"].partition(" (")
            job["kind"], job["word"] = kind, word.removesuffix(")")  # for the filter suggestion
            job["category"] = reason_label(kind)
            job["reason"] = reason_label(job["reason"])
        return cut

    @app.post("/api/filters")
    def adjust_filter(body: FilterBody):
        """One word less in an exclusion list, or one more in title_keywords / locations (from the ✂ tab)."""
        if (body.action == "remove") != (body.field in ("exclude_title_keywords", "exclude_keywords")):
            raise HTTPException(400, t("entrada inválida"))
        try:
            values = list((config_mod.load(config_path).get("search") or {}).get(body.field) or [])
            if body.action == "remove":
                values = [v for v in values if normalize(str(v)) != normalize(body.word)]
            elif not any(normalize(str(v)) == normalize(body.word) for v in values):
                values.append(body.word)
            config_mod.update({("search", body.field): values}, config_path)
        except config_mod.ConfigError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"field": body.field, "values": values}

    @app.get("/api/export.csv")
    def export_csv():
        """Your applications and the jobs you saved, discarded or wrote notes about, for Excel (";", as in Portugal)."""
        names = {"nova": t("Nova"), "guardada": t("Guardada"), "candidatei": t("Candidatei"), "entrevista": t("Entrevista"),
                 "oferta": t("Oferta"), "rejeitada": t("Rejeitada"), "descartada": t("Descartada")}
        out = io.StringIO()
        writer = csv.writer(out, delimiter=";")
        writer.writerow([t("Estado"), t("Empresa"), t("Vaga"), t("Localização"), t("Salário"), t("Fonte"), t("Link"),
                         t("Publicada"), t("Candidatei em"), t("Encaixe"), t("Notas")])
        for job in db.acted_on():
            pay = _salary(job)
            writer.writerow([_cell(v) for v in (
                names.get(job["status"], job["status"]), job["company"], job["title"], job["location"],
                pay["text"] if pay else "", job["source"], job["url"], job["posted_at"] or "",
                (job.get("applied_at") or "")[:10], job["score"], job["notes"])])
        name = t("jobradar-candidaturas.csv")
        return Response("\ufeff" + out.getvalue(), media_type="text/csv; charset=utf-8",  # the BOM: Excel reads UTF-8
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})

    @app.post("/api/jobs/from-url")
    def job_from_url(body: LinkBody):
        """"+ Add job": reads the posting at a link to fill in the form (nothing is saved here)."""
        try:
            with make_client() as client:
                return link.read(body.url, client)
        except link.LinkError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/jobs", status_code=201)
    def add_job(body: NewJob):
        # same link, same job: adding it twice updates it instead of duplicating it
        key = body.url or uuid.uuid4().hex
        job = Job(source="manual", external_id=hashlib.sha1(key.encode()).hexdigest()[:12],
                  company=body.company, title=body.title, location=body.location, url=body.url,
                  description=body.description, posted_at=body.posted_at or None)
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
        try:
            return call(cfg)
        except (message.MessageError, gemini.GeminiError) as exc:
            raise HTTPException(502, str(exc)) from exc
        except Exception as exc:
            if scoring.llm_settings(cfg)["provider"] == "anthropic":
                _claude_error(exc)
            raise

    def ai_text(uid: str, generate) -> dict:
        """Runs one of the AI helpers (message.write or message.interview) for a job."""
        job = db.get(uid)
        if job is None:
            raise HTTPException(404, t("Vaga não encontrada"))
        return {"text": with_ai(lambda cfg: generate(job, cfg, llm_client))}

    @app.post("/api/discover")
    def discover_company(body: CompanyBody):
        """Looks for one company's careers site on the platforms with a public API (a few seconds)."""
        try:
            cfg = config_mod.load(config_path)
        except config_mod.ConfigError as exc:
            raise HTTPException(400, t("Configuração inválida: {error}", error=exc)) from exc
        name = body.company.strip()
        if discover._key(name) in discover.followed(cfg):
            return {"company": name, "followed": True, "found": []}
        search = cfg.get("search") or {}
        places = search.get("locations_primary") or search.get("locations") or []
        with make_client() as client:
            hits = discover.probe(client, name, pause=0.3, places=places)
        return {"company": name, "followed": False, "found": [
            {"platform": kind, "slug": slug, "jobs": jobs, "place": place.title() if place else None,
             "entry": discover.entry(kind, name, slug)}
            for _, kind, slug, jobs, place in hits]}

    @app.post("/api/sources")
    def follow_company(body: SourceBody):
        if body.kind not in discover.ENTRIES:
            raise HTTPException(400, t("A app ainda não lê esta plataforma."))
        try:
            config_mod.add_source(body.kind, body.entry, config_path)
        except config_mod.ConfigError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"ok": True}

    @app.get("/api/market")
    def get_market():
        try:
            cfg = config_mod.load(config_path)  # the profile says which skills you have
        except config_mod.ConfigError as exc:
            raise HTTPException(400, t("Configuração inválida: {error}", error=exc)) from exc
        return skills.market(db.all_jobs(), cfg.get("profile") or {})

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
    def job_message(uid: str, language: Literal["pt", "en"] | None = None):
        """language: the draft's "Rewrite in…" button; by default the message follows the posting."""
        return ai_text(uid, lambda job, cfg, client: message.write(job, cfg, client, language))

    @app.post("/api/jobs/{uid:path}/followup")
    def job_follow_up(uid: str, language: Literal["pt", "en"] | None = None):
        """The follow-up email for an application with no reply yet; the language works as in the message."""
        return ai_text(uid, lambda job, cfg, client: message.follow_up(job, cfg, client, language))

    @app.post("/api/jobs/{uid:path}/interview")
    def job_interview(uid: str):
        return ai_text(uid, message.interview)

    @app.post("/api/jobs/{uid:path}/cv")
    def job_cv(uid: str):
        return ai_text(uid, message.tailor)

    @app.patch("/api/jobs/{uid:path}")
    def update_job(uid: str, body: JobUpdate):
        if body.status is not None and body.status not in STATUSES:
            raise HTTPException(400, t("Estado inválido. Usa: {options}", options=", ".join(STATUSES)))
        job = db.update(uid, status=body.status, notes=body.notes)
        if job is None:
            raise HTTPException(404, t("Vaga não encontrada"))
        for copy in db.copies(uid):  # the same job on another site shows as one card: keep them in step
            db.update(copy, status=body.status, notes=body.notes)
        return job

    @app.post("/api/refresh")
    def refresh():
        if not refresh_lock.acquire(blocking=False):
            raise HTTPException(409, t("Já há uma atualização a correr."))
        try:
            cfg = config_mod.load(config_path)
            runs = run_refresh(cfg, db, score=False, on_progress=lambda state: setattr(app.state, "progress", state),
                               **refresh_kwargs)
            if scoring.llm_available(cfg) or refresh_kwargs.get("llm_client") is not None:
                score_later(cfg)
            return {"runs": runs, "scoring": scoring_lock.locked()}
        except config_mod.ConfigError as exc:
            raise HTTPException(400, t("Configuração inválida: {error}", error=exc)) from exc
        finally:
            refresh_lock.release()

    @app.get("/api/refresh/progress")
    def refresh_progress():
        """How far the search is: how many sources are read, and the ones still being read."""
        state = app.state.progress
        return {"running": refresh_lock.locked(), "total": len(state["sources"]), "done": len(state["done"]),
                "waiting": [s for s in state["sources"] if s not in state["done"]]}

    @app.get("/api/scoring")
    def scoring_status():
        """Whether the AI is still scoring the jobs of the last search (the list reloads when it's done)."""
        return {"running": scoring_lock.locked()}

    @app.get("/api/runs")
    def runs():
        return db.last_runs()

    @app.get("/api/health")
    def source_health():
        """Sources that look broken (the warning above the list), among the ones in the config now."""
        try:
            sources = config_mod.load(config_path).get("sources") or {}
            labels = {source_label(kind, entry) for kind, entries in sources.items() for entry in entries or []}
        except Exception:  # an invalid config shows its own error: judge every source then
            labels = None
        return db.source_health(labels)

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

    @app.get("/api/ai")
    def get_ai():
        """⚙ The AI model: the choices (Google's own list of Gemini models, when the key can read it) and the current one."""
        try:
            cfg = config_mod.load(config_path)
        except config_mod.ConfigError as exc:
            raise HTTPException(400, t("Configuração inválida: {error}", error=exc)) from exc
        settings = scoring.llm_settings(cfg)
        models = (gemini.list_models() if os.environ.get("GEMINI_API_KEY") else []) or scoring.GEMINI_MODELS
        if settings["provider"] == "gemini":
            models = models + [settings["model"]]  # the one in use stays on the list, even if Google drops it
        return {"current": scoring.current_choice(cfg), "choices": scoring.ai_choices(models)}

    @app.put("/api/ai")
    def set_ai(body: AiBody):
        choice = scoring.ai_choice(body.choice)
        if choice is None:
            raise HTTPException(400, t("Modelo de IA desconhecido."))
        try:
            config_mod.update({("scoring.llm", key): choice[key] for key in ("provider", "model", "message_model")},
                              config_path)
        except config_mod.ConfigError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"current": choice["id"]}

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
    def index(k: str = ""):
        if token and _same(k, token):  # the phone app's window, once: from now on the cookie says it's the app
            response = RedirectResponse("/", status_code=303)
            response.set_cookie(TOKEN_COOKIE, token, httponly=True, samesite="strict")
            return response
        app.state.opened.set()
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    app.state.db = db
    return app
