"""Greenhouse job boards, through the public Job Board API: one request per company, descriptions included.
  GET https://boards-api.greenhouse.io/v1/boards/{company}/jobs?content=true
The place is one free-text name: "Lisbon", "Hybrid - Lisbon", "Remote - Portugal".
"""

from __future__ import annotations

import html

import httpx

from ..models import Job
from ..text import normalize, strip_html
from .base import Prefilter

API = "https://boards-api.greenhouse.io/v1/boards/{company}/jobs"


def to_job(company: str, name: str, item: dict) -> Job:
    place = (item.get("location") or {}).get("name") or ""
    words = normalize(place)
    return Job(
        source=f"greenhouse:{company}",
        external_id=str(item["id"]),
        company=name or item.get("company_name") or company,
        title=item.get("title") or "",
        location=place,
        url=item.get("absolute_url") or "",
        posted_at=(item.get("first_published") or item.get("updated_at") or "")[:10] or None,
        description=strip_html(html.unescape(item.get("content") or "")),  # the HTML comes escaped
        work_model="remote" if "remote" in words else "hybrid" if "hybrid" in words else "",
    )


def fetch(client: httpx.Client, entry: dict, prefilter: Prefilter = None) -> list[Job]:
    company = entry["company"]
    resp = client.get(API.format(company=company), params={"content": "true"})
    resp.raise_for_status()
    return [to_job(company, entry.get("name") or "", item) for item in resp.json().get("jobs") or []]
