from __future__ import annotations

from typing import Callable, Optional

import httpx

from ..models import Job

USER_AGENT = "JobRadar/1.0 (personal job search tool)"

# A prefilter decides, from the cheap list data, whether a job is worth an
# extra request for its full description.
Prefilter = Optional[Callable[[Job], bool]]


class SourceSkipped(Exception):
    """Raised when a source cannot run, e.g. a missing API key."""


def make_client() -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(20.0),
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        follow_redirects=True,
    )
