"""SAP SuccessFactors career sites (used by Deloitte Portugal and others).

The job search is a plain HTML page; the RSS feed only has the last 20 jobs and
/services/ is disallowed in robots.txt, so the search page is read instead:
  GET {url}/search/?q=&locationsearch=Lisboa&startrow=0
  GET {url}/job/{slug}/{id}/   (detail, <span class="jobdescription">)
Some sites (EY, Fujitsu) only fill the search with JavaScript from /services/; for
those, `sitemap: true` reads {origin}/sitemap.xml, whose job URLs start with the city:
  /job/Braga-IT-Developer-03/3406550/
"""

from __future__ import annotations

import html
import re
from datetime import datetime
from urllib.parse import unquote, urlsplit

import httpx

from ..models import Job
from ..text import normalize, strip_html
from .base import Prefilter

_ROW_RE = re.compile(r'<tr class="data-row">(.*?)</tr>', re.S)
_TITLE_RE = re.compile(r'<a (?=[^>]*class="jobTitle-link")[^>]*href="([^"]+)"[^>]*>([^<]+)</a>')
_LOCATION_RE = re.compile(r'class="jobLocation">\s*([^<]*?)\s*<')
_DATE_RE = re.compile(r'class="jobDate[^"]*"[^>]*>\s*(\d{1,2}/\d{1,2}/\d{4})')
_TOTAL_RE = re.compile(r'paginationLabel.*?<b>[^<]*</b>\D*<b>(\d+)</b>', re.S)
_ID_RE = re.compile(r"/(\d+)/?$")
_DESCRIPTION_RE = re.compile(r'<span class="jobdescription">(.*?)</span>\s*</div>', re.S)
# pages without the jobdescription span use schema.org microdata instead
_ITEMPROP_TITLE_RE = re.compile(r'itemprop="title"[^>]*>\s*([^<]+?)\s*<')
_ITEMPROP_DESC_RE = re.compile(r'itemprop="description"[^>]*>(.*?)</span>\s*</div>', re.S)
_SITEMAP_JOB_RE = re.compile(r"<loc>([^<]*/job/([^/<]+)/(\d+)/?)</loc>")


def _date(text: str | None) -> str | None:
    try:
        return datetime.strptime(text or "", "%d/%m/%Y").date().isoformat()
    except ValueError:
        return None


def parse_page(base: str, name: str, page: str) -> list[Job]:
    jobs = []
    for row in _ROW_RE.findall(page):
        title = _TITLE_RE.search(row)
        if not title:
            continue
        path = title.group(1)
        location = _LOCATION_RE.search(row)
        posted = _DATE_RE.search(row)
        jobs.append(Job(
            source=f"successfactors:{name}",
            external_id=(_ID_RE.search(path) or title).group(1),
            company=name,
            title=title.group(2).strip(),
            location=location.group(1) if location else "",
            url=base + path,
            posted_at=_date(posted.group(1) if posted else None),
        ))
    return jobs


def _from_search(client: httpx.Client, base: str, name: str, entry: dict, location: str,
                 max_pages: int) -> list[Job]:
    jobs: list[Job] = []
    for _ in range(max_pages):
        resp = client.get(f"{base}/search/", params={
            "q": entry.get("search", ""), "locationsearch": location, "startrow": len(jobs)})
        resp.raise_for_status()
        page = parse_page(base, name, resp.text)
        jobs.extend(page)
        total = _TOTAL_RE.search(resp.text)
        if not page or len(jobs) >= (int(total.group(1)) if total else 0):
            break
    return jobs


def _from_sitemap(client: httpx.Client, base: str, name: str, locations: list[str]) -> list[Job]:
    parts = urlsplit(base)
    resp = client.get(f"{parts.scheme}://{parts.netloc}/sitemap.xml")
    resp.raise_for_status()
    jobs = []
    for url, slug, jid in _SITEMAP_JOB_RE.findall(resp.text):
        slug = html.unescape(unquote(slug))
        location = next((loc for loc in locations if normalize(slug).startswith(normalize(loc) + "-")), None)
        if location is None:
            continue
        jobs.append(Job(
            source=f"successfactors:{name}", external_id=jid, company=name,
            title=slug[len(location) + 1:].replace("-", " "),  # provisional, replaced by the page's title
            location=slug[:len(location)], url=html.unescape(url),
            posted_at=None,  # <lastmod> is when the sitemap was built, not when the job was posted
        ))
    return jobs


def _fill_detail(client: httpx.Client, job: Job) -> None:
    resp = client.get(job.url)
    resp.raise_for_status()
    match = _DESCRIPTION_RE.search(resp.text)
    blocks = [match.group(1)] if match else _ITEMPROP_DESC_RE.findall(resp.text)
    job.description = "\n\n".join(strip_html(b) for b in blocks)
    title = _ITEMPROP_TITLE_RE.search(resp.text)
    if title:
        job.title = html.unescape(title.group(1))


def fetch(
    client: httpx.Client,
    entry: dict,
    prefilter: Prefilter = None,
    max_pages: int = 10,
    max_details: int = 40,
) -> list[Job]:
    base = entry["url"].rstrip("/")
    name = entry["name"]
    # one place or several (e.g. "Lisboa" and "Lisbon"); "" searches every place
    locations = entry.get("location", "")
    locations = locations if isinstance(locations, list) else [locations]
    if entry.get("sitemap"):
        jobs = _from_sitemap(client, base, name, [loc for loc in locations if loc])
    else:
        found: dict[str, Job] = {}
        for location in locations or [""]:
            for job in _from_search(client, base, name, entry, location, max_pages):
                found.setdefault(job.uid, job)
        jobs = list(found.values())

    details = 0
    for job in jobs:
        if details >= max_details:
            break
        if prefilter is None or prefilter(job):
            try:
                _fill_detail(client, job)
            except httpx.HTTPError:
                pass  # keep the job with its list data only
            details += 1
    return jobs
