"""Watched pages: the careers pages of companies without a job platform JobRadar can read.

Each search reads them again and keeps their visible lines. The lines that weren't there before are the change,
and a change matters when one of them has one of the person's words (area or level): the rest (a date, a
testimonial, a counter) is recorded without a warning.
"""

from __future__ import annotations

import re
import time
import urllib.robotparser
from urllib.parse import urlsplit

import httpx

from . import levels, link
from .i18n import t
from .sources.base import USER_AGENT
from .text import contains_term, normalize, strip_html

MIN_TEXT = 200  # characters of visible text: less is a page drawn by JavaScript

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


def check_pages(db, cfg: dict, client, now: str, pause: float = 1.0) -> list[dict]:
    """Read every watched page again and keep what changed. The pages with a change that matters (one of the
    person's words in a new line) in this search. An error stays on its page: the others are still read."""
    words, robots, last, changed = watch_words(cfg), {}, {}, []

    def get(url: str) -> str:
        host = urlsplit(url).netloc
        wait = pause - (time.monotonic() - last.get(host, float("-inf")))
        if wait > 0:  # at most one request a second to the same site
            time.sleep(wait)
        try:
            return link._fetch(url, client)[0]  # never a local or private address, at every redirect
        finally:
            last[host] = time.monotonic()

    for page in db.watched_pages():
        url = page["url"]
        try:
            parts = urlsplit(url)
            origin = f"{parts.scheme}://{parts.netloc}"
            if origin not in robots:
                robots[origin] = urllib.robotparser.RobotFileParser()
                try:
                    robots[origin].parse(get(origin + "/robots.txt").splitlines())
                except (httpx.HTTPError, RuntimeError):
                    robots[origin].parse([])  # no robots.txt (a site down shows up reading the page)
            if not robots[origin].can_fetch(USER_AGENT, url):
                raise link.LinkError(t("o robots.txt do site não deixa ler esta página"))
            lines = page_lines(get(url))
            if sum(map(len, lines)) < MIN_TEXT:
                raise link.LinkError(t("a página precisa de JavaScript: não dá para vigiar"))
        except httpx.HTTPError as exc:
            reason = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else type(exc).__name__
            db.save_page(url, checked_at=now, error=t("Não foi possível abrir a página ({error}).", error=reason))
            continue
        except RuntimeError as exc:  # LinkError, the browser check (BrowserCheck)
            db.save_page(url, checked_at=now, error=str(exc))
            continue
        # the first good read only keeps the text: what's on the page today isn't news
        added = added_lines(page["lines"], lines) if page["lines"] else []
        if not added:  # the current lines, so a line that leaves and comes back counts as new again
            db.save_page(url, checked_at=now, lines=lines)
            continue
        relevant = is_relevant(added, words)
        db.save_page(url, checked_at=now, lines=lines, added=added, relevant=relevant, changed_at=now)
        if relevant:
            changed.append(page)
    return changed
