"""Watched pages: the careers pages of companies without a job platform JobRadar can read.

Each search reads them again and keeps their visible lines. The lines that weren't there before are the change,
and a change matters when one of them has one of the person's words (area or level): the rest (a date, a
testimonial, a counter) is recorded without a warning.
"""

from __future__ import annotations

import re

from . import levels
from .text import contains_term, normalize, strip_html

_HIDDEN = re.compile(r"<(script|style|noscript|nav|header|footer)\b[^>]*>.*?</\1\s*>", re.S | re.I)
_BLOCK = re.compile(r"<(?:/?(?:p|li|div|h\d|td|tr|section|article|ul|ol|table)\b[^>]*|br\s*/?)>", re.I)
_NO_WORDS = re.compile(r"[\d\s/.,:;\-–()%€$©]+")  # numbers, dates, punctuation


def page_lines(page: str) -> list[str]:
    """The page's visible text, one line per block, without menus, header, footer, repeats or lines with no
    words (numbers and dates alone)."""
    text = strip_html(_BLOCK.sub("\n", _HIDDEN.sub(" ", page)))
    seen, out = set(), []
    for line in text.splitlines():
        if len(re.findall(r"[^\W\d_]", line)) < 3 or _NO_WORDS.fullmatch(line) or line in seen:
            continue
        seen.add(line)
        out.append(line)
    return out


def added_lines(old: list[str], new: list[str]) -> list[str]:
    """The lines of `new` that `old` didn't have, in page order."""
    before = set(old)
    return [line for line in new if line not in before]


def watch_words(cfg: dict) -> list[str]:
    """The person's area and level words: the ones that already decide whether a job is theirs."""
    search = cfg.get("search") or {}
    return list(dict.fromkeys(list(search.get("title_keywords") or []) + levels.wanted_words(search)))


def is_relevant(lines: list[str], words: list[str]) -> bool:
    return any(contains_term(normalize(line), word) for line in lines for word in words)
