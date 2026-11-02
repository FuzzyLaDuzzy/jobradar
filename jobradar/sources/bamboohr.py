"""BambooHR career sites (used by Uphold and many smaller companies).

The public careers page calls JSON endpoints that need no login:
  GET https://{site}.bamboohr.com/careers/list          (all open jobs)
  GET https://{site}.bamboohr.com/careers/{id}/detail   (description, datePosted)
"""

from __future__ import annotations

import httpx

from ..models import Job
from ..text import strip_html
from .base import Prefilter

WORK_MODELS = {"0": "on-site", "1": "remote", "2": "hybrid"}


def to_job(name: str, site: str, item: dict) -> Job:
    loc = item.get("location") or {}
    remote = item.get("isRemote") or str(item.get("locationType")) == "1"
    return Job(
        source=f"bamboohr:{name}",
        external_id=str(item["id"]),
        company=name,
        title=(item.get("jobOpeningName") or "").strip(),
        location=", ".join(p for p in (loc.get("city"), loc.get("state")) if p),
        url=f"https://{site}.bamboohr.com/careers/{item['id']}",
        contract=item.get("employmentStatusLabel") or "",
        work_model="remote" if remote else WORK_MODELS.get(str(item.get("locationType")), ""),
    )


def _fill_detail(client: httpx.Client, site: str, job: Job) -> None:
    resp = client.get(f"https://{site}.bamboohr.com/careers/{job.external_id}/detail")
    resp.raise_for_status()
    info = ((resp.json() or {}).get("result") or {}).get("jobOpening") or {}
    job.description = strip_html(info.get("description"))
    job.posted_at = (info.get("datePosted") or "")[:10] or None
    job.url = info.get("jobOpeningShareUrl") or job.url


def fetch(client: httpx.Client, entry: dict, prefilter: Prefilter = None, max_details: int = 40) -> list[Job]:
    site, name = entry["site"], entry["name"]
    resp = client.get(f"https://{site}.bamboohr.com/careers/list")
    resp.raise_for_status()
    jobs = [to_job(name, site, item) for item in (resp.json() or {}).get("result") or []]

    details = 0
    for job in jobs:
        if details >= max_details:
            break
        if prefilter is None or prefilter(job):
            try:
                _fill_detail(client, site, job)
            except httpx.HTTPError:
                pass  # keep the job with its list data only
            details += 1
    return jobs
