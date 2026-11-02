"""Small text helpers shared by filters and scoring."""

from __future__ import annotations

import html
import re
import unicodedata

_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")


def normalize(text: str | None) -> str:
    """Lower-case and strip accents, so 'Estágio' matches 'estagio'."""
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return stripped.lower()


def strip_html(text: str | None) -> str:
    if not text:
        return ""
    text = re.sub(r"<(br|/p|/li|/div|/h\d)\s*/?>", "\n", text, flags=re.I)
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    lines = [_SPACE_RE.sub(" ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def contains_term(normalized_text: str, term: str) -> bool:
    """Whole-word match of `term` inside already-normalised text.

    "lead" matches "tech lead" but not "leader"; "c" matches "C/C++ basics"
    as "c" but not "cloud", "c#" or "c++".
    """
    term = normalize(term).strip()
    if not term:
        return False
    pattern = r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9#+])"
    return re.search(pattern, normalized_text) is not None


def matched_terms(normalized_text: str, terms: list[str]) -> list[str]:
    return [t for t in terms if contains_term(normalized_text, t)]


_COMPANY_SUFFIXES = {"lda", "sa", "s", "a", "unipessoal", "portugal", "pt", "group", "grupo", "gmbh", "inc", "ltd"}


def company_key(name: str | None) -> str:
    """'Eurotux, S.A.' and 'EUROTUX' are the same company: lower case, no accents, punctuation or legal suffix."""
    return " ".join(w for w in re.findall(r"[a-z0-9]+", normalize(name)) if w not in _COMPANY_SUFFIXES)
