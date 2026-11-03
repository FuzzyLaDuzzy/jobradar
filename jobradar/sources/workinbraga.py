"""Work in Braga (workinbraga.pt), the job board of InvestBraga, Braga's economic agency; robots.txt allows it.
Companies post there themselves, Checkmarx too, whose own site refuses automated requests.
  GET https://workinbraga.pt/job-offers?page=N   (cards: node id, regime, title cut at ~50 characters, company)
  GET https://workinbraga.pt/node/{id}           (detail: full title, "Colocado em DD/MM/YYYY", the text of the offer)
Every offer is in Braga: the board is only for Braga.
"""

from __future__ import annotations

import html
import re

import httpx

from ..models import Job
from ..text import strip_html
from .base import Prefilter

BASE = "https://workinbraga.pt"
_CARD_RE = re.compile(r'<a href="https://workinbraga\.pt/node/(\d+)">\s*<div class="job-offer-regime">([^<]*)</div>\s*'
                      r'<div class="job-offer-title">([^<]*)</div>\s*<div class="job-offer-company">([^<]*)</div>')
_TITLE_RE = re.compile(r'<div class="job-offer-header">.*?<h1>([^<]+)</h1>', re.S)
_DATE_RE = re.compile(r"Colocado em (\d{2})/(\d{2})/(\d{4})")
_LOGO_RE = re.compile(r'<div class="company-logo">\s*<img src="([^"]+)"')
_BODY_RE = re.compile(r'<div class="col-sm-12 job-card-content">(.*?)<div class="col-sm-12 job-card-actions">', re.S)


def _text(value: str) -> str:
    return html.unescape(value).strip()


def parse_list(page: str) -> list[Job]:
    return [Job(source="workinbraga", external_id=node, company=_text(company), title=_text(title).rstrip(". …"),
                location="Braga", url=f"{BASE}/node/{node}", contract=_text(regime))
            for node, regime, title, company in _CARD_RE.findall(page)]


def _fill_detail(client: httpx.Client, job: Job) -> None:
    resp = client.get(job.url)
    resp.raise_for_status()
    page = resp.text
    title = _TITLE_RE.search(page)
    if title:
        job.title = _text(title.group(1))  # the list cuts long titles
    date = _DATE_RE.search(page)
    job.posted_at = f"{date.group(3)}-{date.group(2)}-{date.group(1)}" if date else None
    logo = _LOGO_RE.search(page)
    job.logo = BASE + logo.group(1) if logo and logo.group(1).startswith("/") else ""
    body = _BODY_RE.search(page)  # the offer only: the company card beside it has a recruiter's email
    job.description = strip_html(body.group(1)) if body else ""


def fetch(client: httpx.Client, entry: dict, prefilter: Prefilter = None, max_pages: int = 10,
          max_details: int = 30) -> list[Job]:
    jobs: dict[str, Job] = {}
    for page in range(max_pages):
        resp = client.get(f"{BASE}/job-offers", params={"page": page})
        resp.raise_for_status()
        cards = parse_list(resp.text)
        for job in cards:
            jobs.setdefault(job.external_id, job)
        if not cards or f"page={page + 1}" not in resp.text:
            break
    wanted = [job for job in jobs.values() if prefilter is None or prefilter(job)]
    for job in wanted[:max_details]:  # by title: no page for the estate agent or the shop assistant
        try:
            _fill_detail(client, job)
        except httpx.HTTPError:
            pass  # keep the job with its list data only
    return list(jobs.values())
