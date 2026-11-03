"""Workable's public job search (jobs.workable.com), by place: every company on Workable with jobs in the area,
including the ones nobody thought of following. robots.txt only keeps crawlers off the search page itself.
  GET https://jobs.workable.com/api/v1/jobs?location=Braga[&pageToken=...]   (20 jobs a page, with description)
The search is by distance, so it also brings nearby towns; the filters keep the ones in the area.
"""

from __future__ import annotations

import httpx

from ..models import Job
from ..text import strip_html
from .base import Prefilter

API = "https://jobs.workable.com/api/v1/jobs"
WORK_MODELS = {"on_site": "on-site", "hybrid": "hybrid", "remote": "remote"}


def to_job(item: dict) -> Job:
    company = item.get("company") or {}
    sections = (item.get("description"), item.get("requirementsSection"), item.get("benefitsSection"))
    return Job(
        source="workable",
        external_id=item["id"],
        company=company.get("title") or "",
        title=item.get("title") or "",
        location=(item.get("location") or {}).get("city") or "",
        url=item.get("url") or "",
        posted_at=(item.get("created") or "")[:10] or None,
        description=strip_html("".join(s for s in sections if s)),
        contract="" if item.get("employmentType") in (None, "Other") else item["employmentType"],
        work_model=WORK_MODELS.get(item.get("workplace") or "", ""),
        logo=company.get("image") or "",
    )


def fetch(client: httpx.Client, entry: dict, prefilter: Prefilter = None, max_pages: int = 10) -> list[Job]:
    places = entry.get("location") or []
    jobs: dict[str, Job] = {}
    for place in [places] if isinstance(places, str) else places:
        token = None
        for _ in range(max_pages):
            params = {"location": place, **({"pageToken": token} if token else {})}
            resp = client.get(API, params=params, headers={"Accept": "application/json"})
            resp.raise_for_status()
            data = resp.json()
            for item in data.get("jobs") or []:
                jobs.setdefault(item["id"], to_job(item))  # two nearby places can return the same job
            token = data.get("nextPageToken")
            if not token:
                break
    return list(jobs.values())
