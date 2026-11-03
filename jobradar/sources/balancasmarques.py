"""Balanças Marques (Braga) careers, from its own site, which robots.txt allows. The same page lists the
jobs of SDILAB, the software house of the same group (José Pimenta Marques):
  GET https://www.balancasmarques.com/recrutamento   (cards: the title in the share button's data-title,
                                                       then the link to /vagas/{slug}/)
  GET https://www.balancasmarques.com/vagas/{slug}/  (detail: job-meta fields Empresa, Data, Regime, Cidade,
                                                       then the text up to the application form)
"""

from __future__ import annotations

import html
import re

import httpx

from ..models import Job
from ..text import normalize, strip_html
from .base import Prefilter

BASE = "https://www.balancasmarques.com"
_CARD_RE = re.compile(r'data-title="([^"]+)".*?<a href="(/vagas/([^"/]+)/)"', re.S)
_META_RE = re.compile(r'<span class="job-meta-label">\s*([^<]+?)\s*</span>\s*'
                      r'<span class="job-meta-value">\s*([^<]*?)\s*</span>', re.S)
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def parse_list(page: str) -> list[Job]:
    jobs: dict[str, Job] = {}
    for title, path, slug in _CARD_RE.findall(page):
        if "espontanea" in slug:  # a spontaneous application, not a job
            continue
        jobs.setdefault(slug, Job(source="balancasmarques", external_id=slug, company="Balanças Marques",
                                  title=html.unescape(title).strip(), location="", url=BASE + path))
    return list(jobs.values())


def _fill_detail(client: httpx.Client, job: Job) -> None:
    resp = client.get(job.url)
    resp.raise_for_status()
    page = resp.text
    metas = list(_META_RE.finditer(page))
    meta = {normalize(m.group(1)): html.unescape(m.group(2)).strip() for m in metas}
    job.company = meta.get("empresa") or job.company  # "SDILAB" for the group's software house
    job.location = meta.get("cidade", "")
    date = _DATE_RE.search(meta.get("data", ""))
    job.posted_at = date.group(0) if date else None
    regime = meta.get("regime", "")
    job.contract = regime.split("|")[0].strip()
    job.work_model = ("on-site" if "presencial" in normalize(regime) else
                      "remote" if "remot" in normalize(regime) else "hybrid" if "hibrid" in normalize(regime) else "")
    start = metas[-1].end() if metas else page.find("</h1>")
    share = page.find("job-social-share", start)  # the "Partilhar" button after the text, then the form
    end = page.rfind("<button", start, share) if share > 0 else page.find("<form", start)
    job.description = strip_html(page[start:end if end > 0 else None])


def fetch(client: httpx.Client, entry: dict, prefilter: Prefilter = None, max_details: int = 20) -> list[Job]:
    resp = client.get(f"{BASE}/recrutamento")
    resp.raise_for_status()
    jobs = parse_list(resp.text)
    for job in jobs[:max_details]:
        if prefilter is None or prefilter(job):  # by title: no page for the painter or the welder
            try:
                _fill_detail(client, job)
            except httpx.HTTPError:
                pass  # keep the job with its list data only
    return jobs
