"""Landing.jobs (Portuguese tech job board), through its official Atom feed.

  GET https://landing.jobs/feed   (latest ~60 jobs, full description in each entry)
The JSON API is disallowed in robots.txt; the feed is not. Its lj: fields are
never declared as an XML namespace, so the feed is read with regexes, not an XML parser.
"""

from __future__ import annotations

import html
import re

import httpx

from ..models import Job
from ..text import strip_html
from .base import Prefilter

FEED = "https://landing.jobs/feed"
WORK_MODELS = {"partial remote": "hybrid", "full remote": "remote", "onsite job": "on-site"}
_ENTRY_RE = re.compile(r"<entry>(.*?)</entry>", re.S)
_CONTENT_RE = re.compile(r"<content[^>]*>\s*<!\[CDATA\[(.*?)\]\]>", re.S)
_CITY_RE = re.compile(r"<lj:location>\s*<lj:city>(.*?)</lj:city>", re.S)
_LOGO_RE = re.compile(r'<img class="logo" src="([^"]+)"')


def _tag(entry: str, name: str) -> str:
    match = re.search(rf"<{name}>(.*?)</{name}>", entry, re.S)
    return html.unescape(match.group(1).strip()) if match else ""


def to_job(entry: str) -> Job:
    url = _tag(entry, "id")
    content = _CONTENT_RE.search(entry)
    content = content.group(1) if content else ""
    cities = [html.unescape(c.strip()) for c in _CITY_RE.findall(entry) if c.strip()]
    logo = _LOGO_RE.search(content)
    return Job(
        source="landingjobs",
        external_id=url.split("/at/", 1)[-1],
        company=_tag(entry, "name"),
        title=_tag(entry, "title"),
        location=", ".join(cities) or _tag(entry, "lj:city"),
        url=url,
        posted_at=_tag(entry, "published")[:10] or None,
        description=strip_html(content),
        contract=_tag(entry, "lj:job_type"),
        work_model=WORK_MODELS.get(_tag(entry, "lj:remote_policy").lower(), ""),
        logo=logo.group(1) if logo else "",
    )


def fetch(client: httpx.Client, entry: dict, prefilter: Prefilter = None) -> list[Job]:
    resp = client.get(entry.get("feed") or FEED, headers={"Accept": "application/atom+xml"})
    resp.raise_for_status()
    return [to_job(e) for e in _ENTRY_RE.findall(resp.text)]
