"""Net-Empregos (Portugal's largest job board), through its official RSS feed.

  GET https://www.net-empregos.com/rss.asp        (last ~1000 jobs, about one day)
  GET https://www.net-empregos.com/{id}/{slug}/   (schema.org JobPosting in JSON-LD)
robots.txt allows everything and lists the feed. It ignores filters, so the
category filter is applied here, and JobRadar must run daily not to miss jobs.
"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime

import httpx

from ..models import Job
from ..text import normalize, strip_html
from .base import Prefilter

FEED = "https://www.net-empregos.com/rss.asp"
_ITEM_RE = re.compile(r"<item>(.*?)</item>", re.S)
_LD_RE = re.compile(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', re.S)
_ID_RE = re.compile(r"net-empregos\.com/(\d+)/")
_DEFAULT_LOGO = "logo_novo"  # the site's own logo, used when a company has none


def _cdata(item: str, tag: str) -> str:
    match = re.search(rf"<{tag}>\s*(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?\s*</{tag}>", item, re.S)
    return match.group(1).strip() if match else ""


def _field(desc: str, label: str) -> str:
    match = re.search(rf"<b>{label}: </b>\s*(.*?)<br", desc, re.S)
    return html.unescape(match.group(1)).strip() if match else ""


def _date(text: str, fmt: str) -> str | None:
    try:
        return datetime.strptime(text, fmt).date().isoformat()
    except ValueError:
        return None


def to_job(item: str) -> Job:
    link = _cdata(item, "link")
    desc = html.unescape(_cdata(item, "description"))
    jid = _ID_RE.search(link)
    return Job(
        source="netempregos",
        external_id=jid.group(1) if jid else link,
        company=_field(desc, "Empresa") or html.unescape(_cdata(item, "dc:creator")),
        title=html.unescape(_cdata(item, "title")),
        location=_field(desc, "Zona"),
        url=link,
        posted_at=_date(_field(desc, "Data"), "%d-%m-%Y"),
        description=strip_html(_field(desc, "Descrição")),
        contract=_field(desc, "Categoria"),
    )


def _fill_detail(client: httpx.Client, job: Job) -> None:
    resp = client.get(job.url)
    resp.raise_for_status()
    match = _LD_RE.search(resp.content.decode("cp1252", errors="replace"))
    if not match:
        return
    data = json.loads(match.group(1), strict=False)  # raw newlines inside strings
    job.description = strip_html(data.get("description")) or job.description
    job.posted_at = _date((data.get("datePosted") or "").split(" ")[0], "%Y-%m-%d") or job.posted_at
    if data.get("employmentType"):
        job.contract = f"{job.contract}, {data['employmentType'].replace('_', '-').capitalize()}"
    logo = (data.get("hiringOrganization") or {}).get("logo") or ""
    job.logo = "" if _DEFAULT_LOGO in logo else logo


def fetch(client: httpx.Client, entry: dict, prefilter: Prefilter = None, max_details: int = 40) -> list[Job]:
    resp = client.get(entry.get("feed") or FEED)
    resp.raise_for_status()
    feed = resp.content.decode("cp1252", errors="replace")
    categories = [normalize(c) for c in entry.get("categories") or []]
    jobs = [to_job(item) for item in _ITEM_RE.findall(feed)]
    jobs = [j for j in jobs if not categories or normalize(j.contract).startswith(tuple(categories))]

    details = 0
    for job in jobs:
        if details >= max_details:
            break
        if prefilter is None or prefilter(job):
            try:
                _fill_detail(client, job)
            except (httpx.HTTPError, ValueError):
                pass  # keep the job with the feed's snippet
            details += 1
    return jobs
