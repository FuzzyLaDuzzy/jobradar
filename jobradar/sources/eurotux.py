"""Eurotux (Braga) careers, from its own site, which robots.txt allows:
  GET https://eurotux.com/careers/job-opportunities/   (list: one link per job)
  GET https://eurotux.com/careers/{slug}/              (detail: the text between the
                                                        title and "Submit your application")
The place is at the end of the title ("DevOps AWS - Braga (Ref 003-2026)"), when there is one.
The job page's dateModified is when the job was (re)published: the pages are reused.
"""

from __future__ import annotations

import html
import re

import httpx

from ..models import Job
from ..text import normalize, strip_html
from .base import Prefilter

LIST_URL = "https://eurotux.com/careers/job-opportunities/"
_ITEM_RE = re.compile(r'<a href="(https://eurotux\.com/careers/([^"/]+)/)"[^>]*>.*?'
                      r'<span class="elementor-icon-list-text">([^<]+)</span>', re.S)
_REF_RE = re.compile(r"\s*\(Ref[^)]*\)\s*$", re.I)
_PLACE_RE = re.compile(r"^(.*\S)\s+[-–]\s+([^-–]+)$")  # "DevOps AWS - Braga", also with an en dash
# only these count as a place: "Systems Administrator - Enduser" is a job name, not a city
PLACES = {"braga", "lisboa", "lisbon", "porto", "guimaraes", "remote", "remoto"}
_MODIFIED_RE = re.compile(r'"dateModified":"(\d{4}-\d{2}-\d{2})')
_BODY_RE = re.compile(r"<h1[^>]*>.*?</h1>(.*?)(?:Submit your application|Candidata-te|$)", re.S)


def parse_list(page: str) -> list[Job]:
    jobs = []
    for url, slug, text in _ITEM_RE.findall(page):
        if "job" not in slug:  # the same lists link to the privacy policy
            continue
        title = _REF_RE.sub("", html.unescape(text).strip())
        place = ""
        match = _PLACE_RE.match(title)
        if match and normalize(match.group(2)).strip() in PLACES:
            title, place = match.group(1), match.group(2).strip()
        jobs.append(Job(source="eurotux", external_id=slug, company="Eurotux", title=title,
                        location=place, url=url))
    return jobs


def _fill_detail(client: httpx.Client, job: Job) -> None:
    resp = client.get(job.url)
    resp.raise_for_status()
    body = _BODY_RE.search(resp.text)
    job.description = strip_html(body.group(1)) if body else ""
    modified = _MODIFIED_RE.search(resp.text)
    job.posted_at = modified.group(1) if modified else None


def fetch(client: httpx.Client, entry: dict, prefilter: Prefilter = None, max_details: int = 20) -> list[Job]:
    resp = client.get(LIST_URL)
    resp.raise_for_status()
    jobs = parse_list(resp.text)
    for job in jobs[:max_details]:
        if prefilter is None or prefilter(job):
            try:
                _fill_detail(client, job)
            except httpx.HTTPError:
                pass  # keep the job with its list data only
    return jobs
