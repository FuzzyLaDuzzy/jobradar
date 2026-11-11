"""IEFP (iefponline.iefp.pt), the public employment service: its professional internships (estágios profissionais,
the ATIVAR.PT measure), by municipality. No robots.txt; the public search form answers with plain HTML (05/11/2026).
  GET  /IEFP/pesquisas/search.do?cat=ofertaEstagio   (opens the search session: its cookie keeps the pages)
  POST /IEFP/pesquisas/search.do  tipo=OFERTA_ESTAGIO, concelho_facet=BRAGA, resultsPerPage=50
       (cards: id, profession, municipality, field of study, qualification; hidden currentPage and pageCount);
       the next page is the same form with action=1 and the currentPage of the last answer
  GET  /IEFP/pesquisas/detalheOfertasEstagio.do?idOferta=N   (parish, duration, level, number of places)
The offers name neither the employer nor a date: the employer is only shown to the candidates, on IEFPOnline.
"""

from __future__ import annotations

import html
import re

import httpx

from ..models import Job
from .base import Prefilter

BASE = "https://iefponline.iefp.pt/IEFP/pesquisas"
_HTML = {"Accept": "text/html"}
_ARTICLE_RE = re.compile(r'<article[^>]*id="ofertacard_(\d+)"(.*?)</article>', re.S)
_TITLE_RE = re.compile(r'<div class="card-header">.*?<strong>([^<]+)</strong>', re.S)
_PLACE_RE = re.compile(r"Localiza\S*o</div>\s*<div><strong>\s*([^<]+?)\s*</strong>")
_AREA_RE = re.compile(r'<span class="text-capitalize">\s*([^<]+?)\s*</span>')
_QUALIFICATION_RE = re.compile(r'<span class="text-lowercase">\s*([^<]+?)\s*</span>')
_PAGES_RE = re.compile(r'name="(currentPage|pageCount)" value="(\d+)"')
_DETAIL = {  # label in the detail page -> the value under it
    "parish": re.compile(r"</h3>\s*<div>\s*([^<]+?)\s*</div>"),
    "duration": re.compile(r"Dura\S*o</div>\s*<div>\s*<strong>\s*([^<]+?)\s*</strong>"),
    "level": re.compile(r"N\S*vel</div>\s*<div>\s*<strong>\s*([^<]+?)\s*</strong>"),
    "places": re.compile(r"Vagas</small></div>\s*<div[^>]*>\s*(\d+)"),
}
_SMALL_WORDS = {"de", "do", "da", "dos", "das", "e"}


def _text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def _place(value: str) -> str:
    """'VIANA DO CASTELO' -> 'Viana do Castelo'."""
    return " ".join(w.lower() if w.lower() in _SMALL_WORDS else w.capitalize() for w in _text(value).split())


def parse_list(page: str) -> list[Job]:
    jobs = []
    for offer_id, card in _ARTICLE_RE.findall(page):
        title, place = _TITLE_RE.search(card), _PLACE_RE.search(card)
        area, qualification = _AREA_RE.search(card), _QUALIFICATION_RE.search(card)
        if not title:
            continue
        job = Job(source="iefp", external_id=offer_id, company="IEFP (entidade não divulgada)",
                  title=_text(title.group(1)), location=_place(place.group(1)) if place else "",
                  url=f"{BASE}/detalheOfertasEstagio.do?idOferta={offer_id}", contract="Estágio profissional",
                  experience=_text(qualification.group(1)).capitalize() if qualification else "")
        job.description = f"Área de formação: {_text(area.group(1))}." if area else ""
        jobs.append(job)
    return jobs


def _pages(page: str) -> tuple[int, int]:
    found = dict(_PAGES_RE.findall(page))
    return int(found.get("currentPage", 1)), int(found.get("pageCount", 1))


def _fill_detail(client: httpx.Client, job: Job) -> None:
    resp = client.get(job.url, headers=_HTML)
    resp.raise_for_status()
    found = {key: _text(m.group(1)) for key, pattern in _DETAIL.items() if (m := pattern.search(resp.text))}
    if found.get("duration"):
        job.contract = f"Estágio profissional · {found['duration']}"
    if found.get("level") and job.experience:
        job.experience = f"{job.experience} (nível {found['level']})"
    lines = [job.description,
             f"Local: {found['parish']}." if found.get("parish") else "",
             f"Vagas: {found['places']}." if found.get("places") else "",
             "O IEFP não mostra a entidade nem a data: candidatura no IEFPOnline, com registo."]
    job.description = " ".join(line for line in lines if line)


def fetch(client: httpx.Client, entry: dict, prefilter: Prefilter = None, max_pages: int = 10,
          max_details: int = 20) -> list[Job]:
    places = entry.get("location") or []
    jobs: dict[str, Job] = {}
    for place in [places] if isinstance(places, str) else places:
        client.get(f"{BASE}/search.do", params={"cat": "ofertaEstagio"}, headers=_HTML).raise_for_status()
        form = {"tipo": "OFERTA_ESTAGIO", "concelho_facet": place.upper(), "resultsPerPage": "50", "currentPage": "1"}
        for _ in range(max_pages):
            resp = client.post(f"{BASE}/search.do", data=form, headers=_HTML)
            resp.raise_for_status()
            for job in parse_list(resp.text):
                jobs.setdefault(job.external_id, job)
            current, count = _pages(resp.text)
            if current >= count:
                break
            form = {**form, "action": "1", "currentPage": str(current)}
    wanted = [job for job in jobs.values() if prefilter is None or prefilter(job)]
    for job in wanted[:max_details]:  # by title: no page for the cook or the receptionist
        try:
            _fill_detail(client, job)
        except httpx.HTTPError:
            pass  # keep the job with its list data only
    return list(jobs.values())
