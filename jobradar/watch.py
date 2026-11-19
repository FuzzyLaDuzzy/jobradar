"""Watched pages: the careers pages of companies without a job platform JobRadar can read.

Each search reads them again and keeps their visible lines. The lines that weren't there before are the change,
and a change matters when one of them has one of the person's words (area or level): the rest (a date, a
testimonial, a counter) is recorded without a warning.
"""

from __future__ import annotations

import logging
import re
import time
import urllib.robotparser
from urllib.parse import urlsplit

import httpx

from . import levels, link
from .filters import quick_reject
from .i18n import t
from .models import Job
from .sources.base import USER_AGENT
from .text import contains_term, normalize, strip_html

log = logging.getLogger("jobradar")
MIN_TEXT = 200  # characters of visible text: less is a page drawn by JavaScript
TITLE_MAX = 80  # characters: a longer line is a paragraph, not a job's title

# not <header>/<footer>: a job's title often sits in an <article>'s header, and a site's own header and
# footer don't change, so they bring no new lines
_HIDDEN = re.compile(r"<(script|style|noscript|nav)\b[^>]*>.*?</\1\s*>", re.S | re.I)
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


def _without_numbers(line: str) -> str:
    return re.sub(r"\d+", "#", line)


def added_lines(old: list[str], new: list[str]) -> list[str]:
    """The lines of `new` that `old` didn't have, in page order. Numbers don't count: a new date or a counter
    ("Atualizado a 19/11", "13 vagas abertas") isn't a new line."""
    before = {_without_numbers(line) for line in old}
    return [line for line in new if _without_numbers(line) not in before]


def watch_words(cfg: dict) -> list[str]:
    """The person's area and level words: the ones that already decide whether a job is theirs."""
    search = cfg.get("search") or {}
    return list(dict.fromkeys(list(search.get("title_keywords") or []) + levels.wanted_words(search)))


def _like_a_title(line: str) -> bool:
    """Short and not a sentence: a job's title, not a paragraph or a requirement in a list."""
    return len(line) <= TITLE_MAX and not line.endswith((".", ",", ";", ":", "!", "?"))


def _excluded(line: str, search: dict) -> bool:
    """A line the search would cut as a job title (senior, another level, an excluded word, a city outside the
    zone). "Outside the area" doesn't count: a level word alone is enough here."""
    if not search:
        return False
    reason = quick_reject(Job(source="", external_id="", company="", title=line, location="", url=""), search)
    return reason is not None and not reason.startswith("fora da área")


def is_relevant(lines: list[str], words: list[str], search: dict | None = None) -> bool:
    """A line like a job title with one of the person's words, that the search wouldn't cut. The area words are
    made for titles: in a sentence, "ti", "data" or "tecnologia" says nothing about a job."""
    return any(_like_a_title(line) and any(contains_term(normalize(line), word) for word in words)
               and not _excluded(line, search or {}) for line in lines)


def _robots(get, origin: str) -> urllib.robotparser.RobotFileParser | None:
    """The site's robots.txt rules; None when they can't be read. As RFC 9309 says: a missing file (404 and the
    like) allows everything, a server error, a 401/403 or no answer allows nothing."""
    rules = urllib.robotparser.RobotFileParser()
    try:
        rules.parse(get(origin + "/robots.txt").splitlines())
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        if code >= 500 or code in (401, 403):
            return None
        rules.parse([])
    except (httpx.HTTPError, RuntimeError):
        return None
    return rules


def check_pages(db, cfg: dict, client, now: str, pause: float = 1.0) -> list[dict]:
    """Read every watched page again and keep what changed. The pages with a change that matters (one of the
    person's words in a new line) in this search. An error stays on its page: the others are still read."""
    words, search, robots, last, changed = watch_words(cfg), cfg.get("search") or {}, {}, {}, []

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
                robots[origin] = _robots(get, origin)
            if robots[origin] is None:
                raise link.LinkError(t("não deu para ler o robots.txt do site: a página fica por ler"))
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
        except Exception:  # a bug or an odd page: it stays on this page, the others are still read
            log.exception("Falhou a leitura da página vigiada %s", url)
            db.save_page(url, checked_at=now, error=t("Erro inesperado ao ler a página."))
            continue
        # the first good read only keeps the text: what's on the page today isn't news
        added = added_lines(page["lines"], lines) if page["lines"] else []
        relevant = bool(added) and is_relevant(added, words, search)
        # no new lines, or an uninteresting change after one that matters (it mustn't hide it): only the
        # current lines, so a line that leaves and comes back counts as new again
        if not added or (page["relevant"] and not relevant):
            db.save_page(url, checked_at=now, lines=lines)
            continue
        db.save_page(url, checked_at=now, lines=lines, added=added, relevant=relevant, changed_at=now)
        if relevant:
            changed.append(page)
    return changed
