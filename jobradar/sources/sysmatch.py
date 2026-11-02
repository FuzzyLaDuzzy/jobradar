"""Sysmatch (IT consultancy) job board on its own website.

  GET https://www.sysmatch.com/job-opportunities/          (all jobs: title + id)
  GET https://www.sysmatch.com/job-opportunities/{id}/     (schema.org JobPosting in JSON-LD)
The place is only in the title ("Java Developer (M/F) - Lisboa"): the JSON-LD
locality is always the head office, so it is ignored.
"""

from __future__ import annotations

import html
import json
import re

import httpx

from ..models import Job
from ..text import strip_html
from .base import Prefilter

BASE = "https://www.sysmatch.com/job-opportunities/"
_ITEM_RE = re.compile(r'<div class="jobItem"><p class="fw-800">(.*?)</p>.*?href="/job-opportunities/(\d+)"', re.S)
_LD_RE = re.compile(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', re.S)
_MF_RE = re.compile(r"\(?\b[mf]\s*/\s*[mf]\b\)?", re.I)
_SPLIT_RE = re.compile(r"\s+[-–]\s*|\s*[-–]\s+")  # a dash with a space on one side, not "Full-Stack"
_REMOTE_RE = re.compile(r"\b(?:full-)?remot[eo]\b", re.I)
_HYBRID_RE = re.compile(r"\bh[ií]brido\b|\bhybrid\b", re.I)
_ONSITE_RE = re.compile(r"\bpresencial\b", re.I)


def place(title: str) -> tuple[str, str]:
    """(location, work_model) from the end of the title, e.g. "QA - Lisboa - Híbrido (M/F)".

    Simplification: takes the last part after the job name that is more than a work model,
    true for every title seen so far; read the job text if titles like "Java - Banking" appear."""
    # the (M/F) marker also separates the job name from the place: "Frontend Developer (m/f) Lisboa"
    parts = [p for p in _SPLIT_RE.split(_MF_RE.sub(" - ", title)) if p.strip(" -–")]
    location = work_model = ""
    for segment in reversed(parts[1:]):
        if not work_model:
            work_model = "remote" if _REMOTE_RE.search(segment) else "hybrid" if _HYBRID_RE.search(segment) else ""
        for regex in (_REMOTE_RE, _HYBRID_RE, _ONSITE_RE):
            segment = regex.sub("", segment)
        location = segment.strip(" ()/-–")
        if location:
            break
    return location, work_model


def _fill_detail(client: httpx.Client, job: Job) -> None:
    resp = client.get(job.url)
    resp.raise_for_status()
    match = _LD_RE.search(resp.text)
    if not match:
        return
    data = json.loads(match.group(1))
    job.posted_at = (data.get("datePosted") or "")[:10] or None
    job.description = strip_html(data.get("description"))
    job.logo = (data.get("hiringOrganization") or {}).get("logo") or ""


def fetch(
    client: httpx.Client, entry: dict, prefilter: Prefilter = None, max_details: int = 40
) -> list[Job]:
    company = entry.get("company") or "Sysmatch"
    resp = client.get(BASE)
    resp.raise_for_status()
    jobs = []
    for title, jid in _ITEM_RE.findall(resp.text):
        title = html.unescape(title).strip()
        location, work_model = place(title)
        jobs.append(Job(
            source="sysmatch", external_id=jid, company=company, title=title,
            location=location, url=f"{BASE}{jid}/", work_model=work_model,
        ))

    details = 0
    for job in jobs:
        if details >= max_details:
            break
        if prefilter is None or prefilter(job):
            try:
                _fill_detail(client, job)
            except (httpx.HTTPError, ValueError):
                pass  # keep the job with its list data only
            details += 1
    return jobs
