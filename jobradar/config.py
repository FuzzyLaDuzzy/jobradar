from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

import yaml

from . import i18n
from .i18n import t
from .scoring import PROVIDERS
from .sources import FETCHERS, REQUIRED_FIELDS

DEFAULT_CONFIG = Path(os.environ.get("JOBRADAR_CONFIG", "config.yaml"))
EXAMPLE = Path(__file__).resolve().parent.parent / "config.example.yaml"

SEARCH_LISTS = [
    "locations_primary",
    "locations",
    "junior_keywords",
    "exclude_title_keywords",
    "exclude_keywords",
    "title_keywords",
    "exclude_companies",
    "scam_keywords",
]


class ConfigError(ValueError):
    pass


def parse(text: str) -> dict:
    try:
        cfg = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(t("YAML inválido: {error}", error=exc)) from exc
    errors = validate(cfg)
    if errors:
        raise ConfigError("; ".join(errors))
    return cfg


def validate(cfg: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(cfg, dict):
        return [t("A configuração tem de ser um mapa YAML.")]
    search = cfg.get("search")
    if not isinstance(search, dict):
        errors.append(t("Falta a secção '{section}'.", section="search"))
    else:
        for key in SEARCH_LISTS:
            if key in search and not isinstance(search[key], list):
                errors.append(t("{field} tem de ser uma lista.", field=f"search.{key}"))
        if not search.get("locations"):
            errors.append(t("search.locations não pode estar vazio."))
    sources = cfg.get("sources")
    if not isinstance(sources, dict) or not sources:
        errors.append(t("Falta a secção '{section}'.", section="sources"))
    else:
        for kind, entries in sources.items():
            if kind not in FETCHERS:
                errors.append(t("Fonte desconhecida: {kind} (usa {known}).", kind=kind, known=", ".join(FETCHERS)))
                continue
            if not isinstance(entries, list):
                errors.append(t("{field} tem de ser uma lista.", field=f"sources.{kind}"))
                continue
            for i, entry in enumerate(entries):
                if not isinstance(entry, dict):
                    errors.append(t("{field} tem de ser um mapa.", field=f"sources.{kind}[{i}]"))
                    continue
                for field in REQUIRED_FIELDS[kind]:
                    if not entry.get(field):
                        errors.append(t("{entry} precisa de '{field}'.", entry=f"sources.{kind}[{i}]", field=field))
    llm = ((cfg.get("scoring") or {}).get("llm")) or {}
    if llm.get("provider", "anthropic") not in PROVIDERS:
        errors.append(t("scoring.llm.provider tem de ser {options}.", options=" / ".join(PROVIDERS)))
    if cfg.get("language", "pt") not in i18n.LANGUAGES:
        errors.append(t("language tem de ser {options}.", options=" / ".join(i18n.LANGUAGES)))
    return errors


def ensure(path: Path | str = DEFAULT_CONFIG) -> bool:
    """First run: start config.yaml from the example. True if it was created now."""
    path = Path(path)
    if path.exists() or not EXAMPLE.exists():
        return False
    shutil.copyfile(EXAMPLE, path)
    return True


def load(path: Path | str = DEFAULT_CONFIG) -> dict:
    cfg = parse(Path(path).read_text(encoding="utf-8"))
    i18n.use(cfg)
    return cfg


def read_text(path: Path | str = DEFAULT_CONFIG) -> str:
    return Path(path).read_text(encoding="utf-8")


def save_text(text: str, path: Path | str = DEFAULT_CONFIG) -> dict:
    cfg = parse(text)  # raises ConfigError before touching the file
    Path(path).write_text(text, encoding="utf-8")
    i18n.use(cfg)
    return cfg


def set_language(language: str, path: Path | str = DEFAULT_CONFIG) -> dict:
    """Change only the `language:` line, so the comments in config.yaml stay as they are."""
    text = read_text(path)
    line = f"language: {language}"
    new, found = re.subn(r"^language:[ \t]*\w*", line, text, count=1, flags=re.M)
    return save_text(new if found else f"{line}\n{text}", path)


KEYS = ("ITJOBS_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY")
ENV_EXAMPLE = EXAMPLE.parent / ".env.example"


def save_keys(values: dict[str, str], path: Path | str = ".env") -> None:
    """Write KEY=value lines to .env (from the welcome screen), keeping its other lines,
    and use them right away. Values were checked by the caller: no spaces or newlines."""
    path = Path(path)
    if path.exists():
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    else:  # start from the example, so the comments with the links come along
        lines = ENV_EXAMPLE.read_text(encoding="utf-8").splitlines() if ENV_EXAMPLE.exists() else []
    for key, value in values.items():
        line = f"{key}={value}"
        index = next((i for i, old in enumerate(lines) if old.split("=", 1)[0].strip() == key), None)
        if index is None:
            lines.append(line)
        else:
            lines[index] = line
        os.environ[key] = value
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_dotenv(path: Path | str = ".env") -> None:
    """Minimal .env loader (KEY=value lines) so no extra dependency is needed."""
    path = Path(path)
    if not path.exists():
        return
    # utf-8-sig: Windows Notepad may save the file with a BOM before the first key
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        if value:
            os.environ.setdefault(key.strip(), value)
