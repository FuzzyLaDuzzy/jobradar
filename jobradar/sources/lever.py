"""Lever public Postings API (used by Farfetch and others).

GET https://api.lever.co/v0/postings/{site}?mode=json
EU-hosted boards answer on api.eu.lever.co instead, so both hosts are tried.
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from ..models import Job
from ..text import strip_html
from .base import Prefilter

HOSTS = ["https://api.lever.co", "https://api.eu.lever.co"]


def to_job(site: str, posting: dict) -> Job:
    cats = posting.get("categories") or {}
    location = cats.get("location") or ", ".join(cats.get("allLocations") or [])
    created = posting.get("createdAt")
    posted = (
        datetime.fromtimestamp(created / 1000, tz=timezone.utc).date().isoformat()
        if isinstance(created, (int, float))
        else None
    )
    parts = [posting.get("descriptionPlain") or ""]
    for block in posting.get("lists") or []:
        parts.append(f"{block.get('text', '')}\n{strip_html(block.get('content', ''))}")
    parts.append(posting.get("additionalPlain") or "")
    workplace = (posting.get("workplaceType") or "").lower()
    return Job(
        source=f"lever:{site}",
        external_id=posting["id"],
        company=entry_company(site),
        title=(posting.get("text") or "").strip(),
        location=location,
        url=posting.get("hostedUrl") or f"https://jobs.lever.co/{site}/{posting['id']}",
        posted_at=posted,
        description="\n\n".join(p.strip() for p in parts if p and p.strip()),
        contract=cats.get("commitment") or "",
        work_model="" if workplace in ("", "unspecified") else workplace,
    )


def entry_company(site: str) -> str:
    return site.replace("-", " ").title()


def fetch(client: httpx.Client, entry: dict, prefilter: Prefilter = None) -> list[Job]:
    site = entry["site"]
    company = entry.get("company") or entry_company(site)
    postings: list = []
    for host in HOSTS:
        resp = client.get(f"{host}/v0/postings/{site}", params={"mode": "json"})
        if resp.status_code == 404:
            continue
        resp.raise_for_status()
        if "json" not in resp.headers.get("content-type", ""):
            # Lever occasionally answers HTML even with mode=json; try once more.
            resp = client.get(f"{host}/v0/postings/{site}", params={"mode": "json"})
            resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list) and data:
            postings = data
            break
    jobs = [to_job(site, p) for p in postings]
    for job in jobs:
        job.company = company
    return jobs
