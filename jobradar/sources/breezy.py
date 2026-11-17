"""Breezy HR careers sites (Critical Software and many smaller companies); robots.txt allows the job pages.
  GET https://{company}.breezy.hr/json   (every open job: id, name, url, published_date, type, locations)
  GET {url}                              (schema.org JobPosting in JSON-LD: the full description)
A job can be in several places (`locations`); a place may name only its country ("Portugal"), and
`remote_details` says whether it is remote or hybrid.
"""

from __future__ import annotations

import json
import re

import httpx

from ..models import Job
from ..text import strip_html
from .base import Prefilter

_LD_RE = re.compile(r'<script type="application/ld\+json">\s*(.*?)\s*</script>', re.S)


def _places(item: dict) -> str:
    places = []
    for loc in item.get("locations") or [item.get("location") or {}]:
        places.append(loc.get("city") or (loc.get("country") or {}).get("name") or loc.get("name") or "")
    return ", ".join(dict.fromkeys(p for p in places if p))


def _work_model(item: dict) -> str:
    models = {((loc.get("remote_details") or {}).get("value") or "")
              for loc in item.get("locations") or [item.get("location") or {}]}
    return "remote" if "remote" in models else "hybrid" if "hybrid" in models else ""


def to_job(company: str, item: dict) -> Job:
    return Job(
        source=f"breezy:{company}",
        external_id=str(item["id"]),
        company=(item.get("company") or {}).get("name") or company,
        title=(item.get("name") or "").strip(),
        location=_places(item),
        url=item.get("url") or f"https://{company}.breezy.hr/p/{item.get('friendly_id', '')}",
        posted_at=(item.get("published_date") or "")[:10] or None,
        contract=(item.get("type") or {}).get("name") or "",
        work_model=_work_model(item),
    )


def _fill_detail(client: httpx.Client, job: Job) -> None:
    resp = client.get(job.url, headers={"Accept": "text/html"})
    resp.raise_for_status()
    for block in _LD_RE.findall(resp.text):
        try:
            data = json.loads(block, strict=False)
        except ValueError:
            continue
        for item in data if isinstance(data, list) else [data]:
            if isinstance(item, dict) and item.get("@type") == "JobPosting":
                job.description = strip_html(item.get("description"))
                return


def fetch(client: httpx.Client, entry: dict, prefilter: Prefilter = None, max_details: int = 30) -> list[Job]:
    company = entry["company"]
    resp = client.get(f"https://{company}.breezy.hr/json")
    resp.raise_for_status()
    data = resp.json()
    jobs = [to_job(company, item) for item in data if isinstance(item, dict)] if isinstance(data, list) else []
    if entry.get("name"):
        for job in jobs:
            job.company = entry["name"]
    wanted = [job for job in jobs if prefilter is None or prefilter(job)]
    for job in wanted[:max_details]:  # the list has no description: only the jobs worth reading
        try:
            _fill_detail(client, job)
        except httpx.HTTPError:
            pass  # keep the job without its description
    return jobs
