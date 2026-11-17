from __future__ import annotations

import re
from typing import Callable, Optional

import httpx

from ..i18n import t
from ..models import Job

USER_AGENT = "JobRadar/1.0 (personal job search tool)"

# A prefilter decides, from the cheap list data, whether a job is worth an
# extra request for its full description.
Prefilter = Optional[Callable[[Job], bool]]


class SourceSkipped(Exception):
    """Raised when a source cannot run, e.g. a missing API key."""


class BrowserCheck(RuntimeError):
    """The site answered with a bot check that needs a real browser (JavaScript, cookies) instead of its data.
    JobRadar does not get around it: a RuntimeError, so the source shows the message, without a traceback."""


# What the bot-check pages say (Cloudflare's "Just a moment...", Workday's "Security Check")
_CHECK_RE = re.compile(r"just a moment|security check|enable javascript and cookies|challenge-platform", re.I)


def _refuse_browser_checks(response: httpx.Response) -> None:
    """Response hook: a bot-check page in place of the data becomes a BrowserCheck that names the site."""
    if response.status_code not in (403, 429, 503):
        return
    if response.headers.get("cf-mitigated") != "challenge" and not _CHECK_RE.search(response.read().decode(
            "utf-8", "replace")):
        return  # an ordinary refusal (a wrong key, a real rate limit): the source handles it
    raise BrowserCheck(t("{host} pede uma verificação de browser (proteção contra robôs), que o JobRadar não "
                         "contorna. Se continuar, fala com o site ou tira esta fonte das Definições.",
                         host=response.request.url.host))


def make_client(**options) -> httpx.Client:
    """The HTTP client every source uses. `options` go to httpx.Client (tests pass a transport)."""
    return httpx.Client(
        timeout=httpx.Timeout(20.0),
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        follow_redirects=True,
        event_hooks={"response": [_refuse_browser_checks]},
        **options,
    )
