"""Teamtailor career sites (used by Nutrium, Coverflex and many startups), through their RSS feed.

  GET https://{company}.teamtailor.com/jobs.rss    (or {url}/jobs.rss for a site on its own domain,
                                                     e.g. https://join.criticaltechworks.com)
One request has every job with its full description. The tt: fields (city, remote status) are read
with regexes, like the Landing.jobs feed. `remoteStatus` "fully" is a remote job, "hybrid" a hybrid one.
"""

from __future__ import annotations

import html
import re
from email.utils import parsedate_to_datetime

import httpx

from ..models import Job
from ..text import strip_html
from .base import Prefilter

WORK_MODELS = {"fully": "remote", "hybrid": "hybrid", "none": "on-site"}
_ITEM_RE = re.compile(r"<item>(.*?)</item>", re.S)
_CITY_RE = re.compile(r"<tt:city>(.*?)</tt:city>", re.S)
_ID_RE = re.compile(r"/jobs/(\d+)")


def _tag(item: str, name: str) -> str:
    match = re.search(rf"<{name}[^>]*>(.*?)</{name}>", item, re.S)
    text = match.group(1).strip() if match else ""
    return html.unescape(text.removeprefix("<![CDATA[").removesuffix("]]>")).strip()


def _date(text: str) -> str | None:
    try:
        return parsedate_to_datetime(text).date().isoformat()  # "Wed, 14 Oct 2026 10:00:00 +0200"
    except (TypeError, ValueError):
        return None


def to_job(company: str, name: str, item: str) -> Job:
    link = _tag(item, "link")
    job_id = _ID_RE.search(link)
    cities = [html.unescape(c.strip()) for c in _CITY_RE.findall(item) if c.strip()]
    return Job(
        source=f"teamtailor:{company}",
        external_id=job_id.group(1) if job_id else _tag(item, "guid"),
        company=name,
        title=_tag(item, "title"),
        location=", ".join(dict.fromkeys(cities)),
        url=link,
        posted_at=_date(_tag(item, "pubDate")),
        description=strip_html(_tag(item, "description")),
        work_model=WORK_MODELS.get(_tag(item, "remoteStatus").lower(), ""),
    )


def fetch(client: httpx.Client, entry: dict, prefilter: Prefilter = None) -> list[Job]:
    company = entry["company"]
    base = (entry.get("url") or f"https://{company}.teamtailor.com").rstrip("/")
    resp = client.get(f"{base}/jobs.rss", headers={"Accept": "application/rss+xml"})
    resp.raise_for_status()
    return [to_job(company, entry.get("name") or company, item) for item in _ITEM_RE.findall(resp.text)]
