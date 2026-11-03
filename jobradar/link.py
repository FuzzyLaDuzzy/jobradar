"""Read a job from its link, for "+ Add job": most careers sites embed the posting as schema.org JobPosting
(for Google Jobs), with title, company, place, date and text; without it, the page's own title and description.

Only on request, one page at a time. LinkedIn, Indeed and Glassdoor are not opened: their terms forbid it.
"""

from __future__ import annotations

import html
import json
import re
from urllib.parse import urlsplit

import httpx

from .i18n import t
from .text import strip_html

BLOCKED = ("linkedin.com", "indeed.", "glassdoor.")
MAX_BYTES = 3_000_000
_LD_RE = re.compile(r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>", re.S | re.I)


class LinkError(RuntimeError):
    """The page could not be read."""


def _meta(page: str, name: str) -> str:
    for pattern in (rf'<meta[^>]+(?:property|name)=["\']{name}["\'][^>]+content=["\']([^"\']*)',
                    rf'<meta[^>]+content=["\']([^"\']*)["\'][^>]+(?:property|name)=["\']{name}["\']'):
        match = re.search(pattern, page, re.I)
        if match:
            return html.unescape(match.group(1)).strip()
    return ""


def _postings(data) -> list[dict]:
    """Every JobPosting in a JSON-LD block: alone, in a list or in an @graph."""
    items = data if isinstance(data, list) else [data]
    found = []
    for item in items:
        if not isinstance(item, dict):
            continue
        kind = item.get("@type")
        if kind == "JobPosting" or (isinstance(kind, list) and "JobPosting" in kind):
            found.append(item)
        found += _postings(item.get("@graph") or [])
    return found


def _name(value) -> str:
    if isinstance(value, dict):
        return str(value.get("name") or "")
    return str(value or "")


def _place(posting: dict) -> str:
    places = posting.get("jobLocation") or []
    parts: list[str] = []
    for place in places if isinstance(places, list) else [places]:
        address = (place or {}).get("address") if isinstance(place, dict) else None
        if isinstance(address, str):
            parts.append(address)
        elif isinstance(address, dict):
            parts += [_name(address.get(k)) for k in ("addressLocality", "addressRegion", "addressCountry")]
    if posting.get("jobLocationType") == "TELECOMMUTE":
        parts.append("Remote")
    seen: list[str] = []
    for part in (p.strip() for p in parts):
        if part and part not in seen:
            seen.append(part)
    return ", ".join(seen)


def parse(page: str) -> dict:
    """The job's fields from a page's HTML (empty strings for what it doesn't say)."""
    for block in _LD_RE.findall(page):
        try:
            data = json.loads(block.strip())
        except ValueError:
            continue
        for posting in _postings(data):
            return {"title": strip_html(html.unescape(str(posting.get("title") or ""))),
                    "company": _name(posting.get("hiringOrganization")),
                    "location": _place(posting),
                    "posted_at": str(posting.get("datePosted") or "")[:10],
                    "description": strip_html(html.unescape(str(posting.get("description") or "")))}
    title = _meta(page, "og:title")
    if not title:
        match = re.search(r"<title[^>]*>(.*?)</title>", page, re.S | re.I)
        title = html.unescape(match.group(1)).strip() if match else ""
    return {"title": title, "company": _meta(page, "og:site_name"), "location": "", "posted_at": "",
            "description": _meta(page, "og:description") or _meta(page, "description")}


def read(url: str, client: httpx.Client) -> dict:
    host = (urlsplit(url).hostname or "").lower()
    if any(name in host for name in BLOCKED):
        raise LinkError(t("Este site não deixa ler as vagas por programas: preenche os campos à mão."))
    try:
        resp = client.get(url)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise LinkError(t("Não foi possível abrir o link ({error}).", error=type(exc).__name__)) from exc
    if len(resp.content) > MAX_BYTES:
        raise LinkError(t("A página é grande demais para ler."))
    job = parse(resp.text)
    if not job["title"]:
        raise LinkError(t("Não encontrei uma vaga nesta página: preenche os campos à mão."))
    limits = {"title": 200, "company": 200, "location": 200, "posted_at": 10, "description": 20000}
    return {key: value[:limits[key]] for key, value in job.items()} | {"url": str(resp.url)}
