"""Find companies hiring in your area that publish their jobs on a careers platform
with a public API, and print the config.yaml lines to follow them.

    python -m jobradar descobrir                  # companies already seen in your area
    python -m jobradar descobrir Uphold "F3M"     # plus these names
"""

from __future__ import annotations

import re
import time
from typing import Callable

import httpx

from .db import Database
from .filters import location_status
from .i18n import t
from .models import Job
from .text import normalize

# platform: (URL to probe, how many jobs its answer lists)
PROBES = {
    "bamboohr": ("https://{slug}.bamboohr.com/careers/list", lambda r: len(r.json().get("result") or [])),
    "lever": ("https://api.lever.co/v0/postings/{slug}?mode=json",
              lambda r: len(r.json()) if isinstance(r.json(), list) else 0),
    "smartrecruiters": ("https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100",
                        lambda r: r.json().get("totalFound") or 0),
    "greenhouse": ("https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", lambda r: len(r.json().get("jobs") or [])),
    "workable": ("https://apply.workable.com/api/v1/widget/accounts/{slug}", lambda r: len(r.json().get("jobs") or [])),
    "ashby": ("https://api.ashbyhq.com/posting-api/job-board/{slug}", lambda r: len(r.json().get("jobs") or [])),
    "recruitee": ("https://{slug}.recruitee.com/api/offers/", lambda r: len(r.json().get("offers") or [])),
    "personio": ("https://{slug}.jobs.personio.de/xml", lambda r: r.text.count("<position>")),
    "breezy": ("https://{slug}.breezy.hr/json", lambda r: len(r.json()) if isinstance(r.json(), list) else 0),
}
# platforms JobRadar already reads: the entry to paste under `sources:` in config.yaml
CONFIG = {
    "bamboohr": "  bamboohr:\n    - name: {name}\n      site: {slug}",
    "lever": "  lever:\n    - site: {slug}\n      company: {name}",
    "smartrecruiters": "  smartrecruiters:\n    - company: {slug}\n      country: pt",
    "recruitee": "  recruitee:\n    - company: {slug}\n      name: {name}",
}
_SUFFIXES = {"lda", "sa", "s", "a", "unipessoal", "portugal", "pt", "group", "grupo"}


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", normalize(name))


def slugs(name: str) -> list[str]:
    """How a company is usually named on these platforms: "Balanças Marques, S.A." ->
    balancasmarques, balancas-marques."""
    words = [w for w in re.findall(r"[a-z0-9]+", normalize(name)) if w not in _SUFFIXES]
    return list(dict.fromkeys(["".join(words), "-".join(words)])) if words else []


def companies_in_area(db: Database, search: dict, known: set[str]) -> list[str]:
    names: dict[str, str] = {}
    for row in db.conn.execute("SELECT DISTINCT source, company, title, location, description, work_model FROM jobs"):
        job = Job(source=row["source"], external_id="", company=row["company"] or "", title=row["title"] or "",
                  location=row["location"] or "", url="", description=row["description"] or "",
                  work_model=row["work_model"] or "")
        if job.company and _key(job.company) not in known and location_status(job, search) is True:
            names[_key(job.company)] = job.company
    return sorted(names.values())


def probe(client: httpx.Client, name: str, pause: float, places: list[str] = ()) -> list[tuple]:
    """(name, platform, slug, jobs, the first of your places its answer mentions, or None)"""
    found = []
    for slug in slugs(name):
        for kind, (url, count) in PROBES.items():
            try:
                resp = client.get(url.format(slug=slug))
                jobs = count(resp) if resp.status_code == 200 else 0
            except (httpx.HTTPError, ValueError, AttributeError):
                jobs = 0  # unknown company: 404, a marketing page instead of JSON, no such host...
            if jobs:
                text = normalize(resp.text)
                found.append((name, kind, slug, jobs, next((p for p in places if normalize(p) in text), None)))
            time.sleep(pause)  # stay well under one request per second on each platform
    return found


def run(cfg: dict, db: Database, client: httpx.Client, extra=(), pause: float = 0.3,
        out: Callable[[str], None] = print) -> list[tuple]:
    known = {_key(v) for entries in (cfg.get("sources") or {}).values() for e in entries or []
             for v in e.values() if isinstance(v, str)}
    search = cfg.get("search") or {}
    places = search.get("locations_primary") or search.get("locations") or []
    names = sorted(set(companies_in_area(db, search, known)) | set(extra))
    out(t("A procurar {n} empresas em {platforms} plataformas (demora uns segundos por empresa)...",
          n=len(names), platforms=len(PROBES)))
    found = []
    for name in names:
        for hit in probe(client, name, pause, places):
            _, kind, slug, jobs, place = hit
            where = t(", menciona {place}", place=place.title()) if place else ""
            head = t("{name}: {platform}/{slug} ({jobs} vagas{where}).", name=name, platform=kind, slug=slug,
                     jobs=jobs, where=where)
            if kind in CONFIG:
                out(f"\n{head} " + t("Para a seguir, acrescenta às `sources` do config.yaml:")
                    + f"\n{CONFIG[kind].format(name=name, slug=slug)}")
            else:
                out(f"\n{head} " + t("O JobRadar ainda não lê esta plataforma."))
            found.append(hit)
    if not found:
        out(t("Nenhuma das empresas tem um site de carreiras numa plataforma conhecida."))
    return found
