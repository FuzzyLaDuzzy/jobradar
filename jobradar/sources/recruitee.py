"""Recruitee career sites (used by Mercedes-Benz.io and many startups).

One public JSON endpoint has every open job with its full description:
  GET https://{company}.recruitee.com/api/offers/
A job can be offered in several places: `location` names one ("Hybrid, Lisboa, Portugal")
but `locations` lists them all (Lisboa and Braga), so the location comes from that list.
"""

from __future__ import annotations

import httpx

from ..models import Job
from ..text import strip_html
from .base import Prefilter

_NOT_A_PLACE = {"hybrid", "remote", "on-site", "onsite"}  # Recruitee puts these in `city`


def _places(item: dict) -> str:
    places = []
    for loc in item.get("locations") or []:
        city = loc.get("city") if (loc.get("city") or "").lower() not in _NOT_A_PLACE else ""
        places.append(city or loc.get("state") or "")
    if not any(places):
        city = item.get("city") if (item.get("city") or "").lower() not in _NOT_A_PLACE else ""
        places = [city or item.get("state") or item.get("location") or ""]
    return ", ".join(dict.fromkeys(p for p in places if p))


def _label(code: str | None) -> str:
    return (code or "").replace("_", " ").capitalize()  # "fulltime_permanent" -> "Fulltime permanent"


def to_job(company: str, item: dict) -> Job:
    work_model = "remote" if item.get("remote") else "hybrid" if item.get("hybrid") else (
        "on-site" if item.get("on_site") else "")
    return Job(
        source=f"recruitee:{company}",
        external_id=str(item["id"]),
        company=item.get("company_name") or company,
        title=(item.get("title") or "").strip(),
        location=_places(item),
        url=item.get("careers_url") or f"https://{company}.recruitee.com/o/{item.get('slug', '')}",
        posted_at=(item.get("published_at") or item.get("created_at") or "")[:10] or None,
        description="\n\n".join(strip_html(item.get(k)) for k in ("description", "requirements") if item.get(k)),
        contract=_label(item.get("employment_type_code")),
        experience=_label(item.get("experience_code")),
        work_model=work_model,
    )


def fetch(client: httpx.Client, entry: dict, prefilter: Prefilter = None) -> list[Job]:
    company = entry["company"]
    resp = client.get(f"https://{company}.recruitee.com/api/offers/")
    resp.raise_for_status()
    jobs = [to_job(company, item) for item in (resp.json() or {}).get("offers") or []]
    if entry.get("name"):  # the config's name instead of the legal one ("Mercedes-Benz.io GmbH")
        for job in jobs:
            job.company = entry["name"]
    return jobs
