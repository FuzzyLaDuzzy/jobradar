"""Workday career sites (used by Euronext and many large employers).

The public careers page calls a JSON endpoint that needs no login:
  POST https://{host}/wday/cxs/{tenant}/{site}/jobs   {limit<=20, offset, searchText, appliedFacets}
  GET  https://{host}/wday/cxs/{tenant}/{site}{externalPath}   (job detail)
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from urllib.parse import urlparse

import httpx

from ..models import Job
from ..text import strip_html
from .base import Prefilter

PAGE = 20  # Workday rejects limits above 20
_LOCALE_RE = re.compile(r"^[a-z]{2}-[A-Z]{2}$")
_DAYS_RE = re.compile(r"(\d+)\+?\s+days?\s+ago", re.I)


def parse_board(url: str, tenant: str | None = None) -> tuple[str, str, str]:
    """Return (host, tenant, site) from a careers URL like
    https://hrhub.wd3.myworkdayjobs.com/en-US/Euronext_Career_Page"""
    parsed = urlparse(url)
    segments = [s for s in parsed.path.split("/") if s]
    if segments and _LOCALE_RE.match(segments[0]):
        segments = segments[1:]
    if not segments:
        raise ValueError(f"URL do Workday sem nome do site: {url}")
    host = parsed.netloc
    return host, tenant or host.split(".")[0], segments[0]


def posted_on_to_date(text: str | None, today: date | None = None) -> str | None:
    if not text:
        return None
    today = today or date.today()
    low = text.lower()
    if "today" in low:
        return today.isoformat()
    if "yesterday" in low:
        return (today - timedelta(days=1)).isoformat()
    match = _DAYS_RE.search(low)
    if match:
        return (today - timedelta(days=int(match.group(1)))).isoformat()
    return None


def fetch(
    client: httpx.Client,
    entry: dict,
    prefilter: Prefilter = None,
    max_pages: int = 25,
    max_details: int = 60,
    today: date | None = None,
) -> list[Job]:
    host, tenant, site = parse_board(entry["url"], entry.get("tenant"))
    name = entry.get("name") or site
    api = f"https://{host}/wday/cxs/{tenant}/{site}"
    # one search per place (e.g. "Lisboa" and "Lisbon"); "" lists every job
    searches = entry.get("search", "")
    searches = searches if isinstance(searches, list) else [searches]

    found: dict[str, Job] = {}
    for text in searches or [""]:
        total = None
        offset = 0
        for _ in range(max_pages):
            body = {"limit": PAGE, "offset": offset, "searchText": text, "appliedFacets": {}}
            resp = client.post(f"{api}/jobs", json=body)
            resp.raise_for_status()
            data = resp.json()
            postings = data.get("jobPostings") or []
            if total is None:
                total = data.get("total") or 0
            for p in postings:
                path = p.get("externalPath") or ""
                bullets = p.get("bulletFields") or []
                job = Job(
                    source=f"workday:{name}",
                    external_id=bullets[0] if bullets else path,
                    company=name,
                    title=(p.get("title") or "").strip(),
                    location=p.get("locationsText") or "",
                    url=f"https://{host}/{site}{path}",
                    posted_at=posted_on_to_date(p.get("postedOn"), today),
                )
                job._path = path  # type: ignore[attr-defined]
                found.setdefault(job.uid, job)
            offset += PAGE
            if not postings or len(postings) < PAGE or offset >= total:
                break
    jobs = list(found.values())

    details = 0
    for job in jobs:
        if details >= max_details:
            break
        if prefilter is None or prefilter(job):
            try:
                resp = client.get(f"{api}{job._path}")  # type: ignore[attr-defined]
                resp.raise_for_status()
                info = (resp.json() or {}).get("jobPostingInfo") or {}
                job.description = strip_html(info.get("jobDescription"))
                locs = [info.get("location")] + list(info.get("additionalLocations") or [])
                locs = [loc for loc in locs if loc]
                if locs:
                    job.location = ", ".join(locs)
                job.contract = info.get("timeType") or job.contract
            except httpx.HTTPError:
                pass
            details += 1
    return jobs
