from __future__ import annotations

import json
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
    profile = cfg.get("profile") if isinstance(cfg.get("profile"), dict) else {}
    for key in ("skills", "focus", "education", "projects", "experience"):
        if key in profile and not isinstance(profile[key], list):
            errors.append(t("{field} tem de ser uma lista.", field=f"profile.{key}"))
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


def _scalar(text: str) -> str:
    """Plain when YAML reads it back as the same text, quoted otherwise ("c#", "yes", "a: b"...)."""
    try:
        if text and yaml.safe_load(f"[{text}]") == [text]:
            return text
    except yaml.YAMLError:
        pass
    return json.dumps(text, ensure_ascii=False)  # a JSON string is also a YAML string


def _render(key: str, value, indent: int, width: int = 110) -> str:
    """`key: value` in config.yaml's own style: lists in [...] wrapped and aligned under the
    first item, text with line breaks as a | block."""
    pad = " " * indent
    if isinstance(value, bool):
        return f"{key}: {'true' if value else 'false'}"
    if isinstance(value, list):
        head = f"{key}: ["
        lines, line = [], head
        for i, item in enumerate(value):
            word = _scalar(str(item)) + ("," if i < len(value) - 1 else "]")
            if line != head and indent + len(line) + 1 + len(word) > width:
                lines.append(line.rstrip())
                line = " " * len(head) + word
            else:
                line += ("" if line == head else " ") + word
        lines.append(line if value else f"{key}: []")
        return f"\n{pad}".join(lines)
    value = str(value).strip()
    if "\n" in value:
        return f"{key}: |\n" + "\n".join(f"{pad}  {line}".rstrip() for line in value.splitlines())
    return f"{key}: {_scalar(value) if value else chr(34) * 2}"


def _same(old, new) -> bool:
    if isinstance(old, str) and isinstance(new, str):  # a | block reads back with a final line break
        return old.strip() == new.strip()
    return old == new or (old is None and new in ("", []))


def update(changes: dict[tuple[str, str], object], path: Path | str = DEFAULT_CONFIG) -> dict:
    """Change some values of config.yaml (the 👤 Profile screen) and leave every other character
    as it was: comments, order, line breaks. PyYAML says where each value starts and ends."""
    text = read_text(path)
    current = yaml.safe_load(text) or {}
    root = yaml.compose(text)
    sections = {k.value: v for k, v in root.value} if isinstance(root, yaml.MappingNode) else {}
    edits: list[tuple[int, int, str]] = []
    for section in dict.fromkeys(s for s, _ in changes):
        wanted = {k: v for (s, k), v in changes.items() if s == section
                  and not _same((current.get(section) or {}).get(k), v)}
        mapping = sections.get(section)
        if wanted and section not in sections:  # e.g. no `profile:` yet: a new section at the end
            lines = [f"  {_render(k, v, 2)}" for k, v in wanted.items() if v not in ("", [], None)]
            sep = "" if text.endswith("\n") else "\n"
            edits.append((len(text), len(text), f"{sep}{section}:\n" + "\n".join(lines) + "\n"))
            continue
        if not wanted or not isinstance(mapping, yaml.MappingNode) or mapping.flow_style or not mapping.value:
            if wanted:
                raise ConfigError(t("Não foi possível gravar: a secção '{section}' do config.yaml tem um formato "
                                    "que a app não sabe editar. Edita-a no ⚙.", section=section))
            continue
        indent = mapping.value[0][0].start_mark.column
        found = {k.value: (k, v) for k, v in mapping.value}
        added = []
        for key, value in wanted.items():
            if key in found:
                k, v = found[key]
                end_nl = text[v.end_mark.index - 1] == "\n"  # a | block ends with its line break
                new = _render(key, value, indent) + ("\n" if end_nl else "")
                edits.append((k.start_mark.index, v.end_mark.index, new))
            elif value not in ("", [], None):  # an empty field doesn't add a line
                added.append(" " * indent + _render(key, value, indent))
        if added:
            end = mapping.value[-1][1].end_mark.index
            at_line_start = text[end - 1] == "\n"
            edits.append((end, end, ("" if at_line_start else "\n") + "\n".join(added) + ("\n" if at_line_start else "")))
    for start, end, new in sorted(edits, reverse=True):
        text = text[:start] + new + text[end:]
    cfg = parse(text)
    for (section, key), value in changes.items():  # what YAML reads back must be what was asked
        if not _same((cfg.get(section) or {}).get(key), value):
            raise ConfigError(t("Não foi possível gravar {field}: confirma o valor.", field=f"{section}.{key}"))
    return save_text(text, path)


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
