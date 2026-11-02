"""Randstad Portugal (recruiter, includes Randstad Digital), through its official RSS feed.

  GET https://www.randstad.pt/empregos/rss/   (all open jobs, about three weeks; city and region per job)
  GET {link}                                  (schema.org JobPosting in JSON-LD: full description)
The client company is never named, so jobs show "Randstad" as the company.
"""

from __future__ import annotations

import html
import json
import re
from email.utils import parsedate_to_datetime

import httpx

from ..models import Job
from ..text import normalize, strip_html
from .base import Prefilter

FEED = "https://www.randstad.pt/empregos/rss/"
_ITEM_RE = re.compile(r"<item>(.*?)</item>", re.S)
_LD_RE = re.compile(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', re.S)


def _tag(item: str, name: str) -> str:
    match = re.search(rf"<{name}>\s*(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?\s*</{name}>", item, re.S)
    return html.unescape(match.group(1)).strip() if match else ""


def to_job(company: str, item: str) -> Job:
    city, region = _tag(item, "city"), _tag(item, "region")
    where = normalize(city)
    try:
        posted = parsedate_to_datetime(_tag(item, "pubDate")).date().isoformat()
    except (TypeError, ValueError):
        posted = None
    return Job(
        source="randstad",
        external_id=_tag(item, "jobId") or _tag(item, "guid"),
        company=company,
        title=_tag(item, "title"),
        location=", ".join(p for p in (city, region) if p),
        url=_tag(item, "link"),
        posted_at=posted,
        description=strip_html(_tag(item, "description")),
        work_model="remote" if "remot" in where else "hybrid" if "hibrid" in where else "",
    )


def _fill_detail(client: httpx.Client, job: Job) -> None:
    resp = client.get(job.url)
    resp.raise_for_status()
    for block in _LD_RE.findall(resp.text):
        data = json.loads(block, strict=False)
        if "JobPosting" not in str(data.get("@type")):
            continue
        parts = [strip_html(data.get(k)) for k in ("description", "responsibilities", "skills")]
        job.description = "\n\n".join(p for p in parts if p) or job.description
        if data.get("employmentType"):
            job.contract = data["employmentType"].replace("_", "-").capitalize()
        return


def fetch(client: httpx.Client, entry: dict, prefilter: Prefilter = None, max_details: int = 40) -> list[Job]:
    resp = client.get(entry.get("feed") or FEED)
    resp.raise_for_status()
    company = entry.get("company") or "Randstad"
    jobs = [to_job(company, item) for item in _ITEM_RE.findall(resp.text)]

    details = 0
    for job in jobs:
        if details >= max_details:
            break
        if prefilter is None or prefilter(job):
            try:
                _fill_detail(client, job)
            except (httpx.HTTPError, ValueError):
                pass  # keep the job with the feed's snippet
            details += 1
    return jobs
