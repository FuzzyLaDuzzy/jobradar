"""SmartRecruiters public Posting API (used by Bosch and many others).

List:   GET https://api.smartrecruiters.com/v1/companies/{company}/postings
Detail: GET https://api.smartrecruiters.com/v1/companies/{company}/postings/{id}
No API key needed. The server caps `limit` at 100 and echoes the value it used.

Search: GET https://jobs.smartrecruiters.com/sr-jobs/search?keyword=Braga  (every company, by place;
        each result links to its detail above)
"""

from __future__ import annotations

import httpx

from ..models import Job
from ..text import strip_html
from .base import Prefilter

API = "https://api.smartrecruiters.com/v1/companies/{company}/postings"
SEARCH = "https://jobs.smartrecruiters.com/sr-jobs/search"


def _location(loc: dict) -> str:
    if loc.get("fullLocation"):
        parts = [p.strip() for p in loc["fullLocation"].split(",")]
        return ", ".join(p for p in parts if p)
    parts = [loc.get("city"), loc.get("region"), (loc.get("country") or "").upper()]
    return ", ".join(p for p in parts if p)


def _work_model(loc: dict) -> str:
    if loc.get("remote"):
        return "remote"
    if loc.get("hybrid"):
        return "hybrid"
    return ""


def to_job(company: str, posting: dict) -> Job:
    loc = posting.get("location") or {}
    return Job(
        source=f"smartrecruiters:{company}",
        external_id=str(posting["id"]),
        company=(posting.get("company") or {}).get("name") or company,
        title=(posting.get("name") or "").strip(),
        location=_location(loc),
        url=f"https://jobs.smartrecruiters.com/{company}/{posting['id']}",
        posted_at=(posting.get("releasedDate") or "")[:10] or None,
        contract=(posting.get("typeOfEmployment") or {}).get("label", "") or "",
        experience=(posting.get("experienceLevel") or {}).get("label", "") or "",
        work_model=_work_model(loc),
    )


def _fill_detail(client: httpx.Client, company: str, job: Job) -> None:
    resp = client.get(f"{API.format(company=company)}/{job.external_id}")
    resp.raise_for_status()
    data = resp.json()
    sections = ((data.get("jobAd") or {}).get("sections")) or {}
    texts = []
    for key in ("jobDescription", "qualifications", "additionalInformation"):
        section = sections.get(key) or {}
        if section.get("text"):
            texts.append(strip_html(section["text"]))
    job.description = "\n\n".join(texts)
    if data.get("postingUrl"):
        job.url = data["postingUrl"]
    # the search's results leave these empty
    job.contract = job.contract or (data.get("typeOfEmployment") or {}).get("label", "") or ""
    job.experience = job.experience or (data.get("experienceLevel") or {}).get("label", "") or ""


def fetch(
    client: httpx.Client,
    entry: dict,
    prefilter: Prefilter = None,
    max_pages: int = 30,
    max_details: int = 80,
) -> list[Job]:
    company = entry["company"]
    params: dict = {"limit": 100, "offset": 0}
    for key in ("country", "city", "q"):
        if entry.get(key):
            params[key] = entry[key]

    jobs: list[Job] = []
    offset = 0
    for _ in range(max_pages):
        params["offset"] = offset
        resp = client.get(API.format(company=company), params=params)
        resp.raise_for_status()
        data = resp.json()
        content = data.get("content") or []
        jobs.extend(to_job(company, p) for p in content)
        limit = data.get("limit") or 100
        offset += limit
        if not content or len(content) < limit or offset >= (data.get("totalFound") or 0):
            break

    details = 0
    for job in jobs:
        if details >= max_details:
            break
        if prefilter is None or prefilter(job):
            try:
                _fill_detail(client, company, job)
            except httpx.HTTPError:
                pass  # keep the job with its list data only
            details += 1
    return jobs


def search(client: httpx.Client, entry: dict, prefilter: Prefilter = None, max_details: int = 80) -> list[Job]:
    """SmartRecruiters' public job search, by place (`keyword`, from `search`): every company on SmartRecruiters
    with jobs there, like the Workable search. The companies followed on their own (`skip`) are left to them."""
    skip = {name.lower() for name in entry.get("skip") or []}
    places = entry.get("keyword") or []
    jobs: dict[str, tuple[str, Job]] = {}
    for place in [places] if isinstance(places, str) else places:
        # ponytail: no paging works here (offset, page...), so only the 100 newest per place: enough twice a day
        resp = client.get(SEARCH, params={"keyword": place, "limit": 100}, headers={"Accept": "application/json"})
        resp.raise_for_status()
        for item in resp.json().get("content") or []:
            company = (item.get("company") or {}).get("identifier") or ""
            details = (item.get("actions") or {}).get("details") or ""
            if not company or not details or company.lower() in skip:
                continue
            # the search has its own id: the detail link carries the posting's, as the company API knows it
            job = to_job(company, {**item, "id": details.rstrip("/").rsplit("/", 1)[-1]})
            job.source = "smartrecruiters_search"
            jobs.setdefault(job.external_id, (company, job))

    wanted = [(company, job) for company, job in jobs.values() if prefilter is None or prefilter(job)]
    for company, job in wanted[:max_details]:
        try:
            _fill_detail(client, company, job)
        except httpx.HTTPError:
            pass  # keep the job with its list data only
    return [job for _, job in jobs.values()]
