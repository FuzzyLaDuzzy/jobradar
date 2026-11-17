"""Sapo Emprego (emprego.sapo.pt), one of Portugal's largest job boards, for every field; robots.txt allows /offers.
The search page carries its results as JSON in the attributes of a Vue component, 9 to a page (17/11/2026):
  GET https://emprego.sapo.pt/offers?local=braga,porto&categoria=informatica-tecnologias&pagina=N
      :offers='[...]'      id, offer_name, company_name, location, publication_date, remote_work, link...
      :pagination='{...}'  total, page, size
  GET {link}   (schema.org JobPosting in JSON-LD: the full description and the company's logo)
`local` takes districts only: a town such as "guimaraes" is ignored and the search covers the whole country.
So, as for ITJobs, the districts come from the place names in `search.locations` that are districts.
`categoria` takes the site's category slugs (CATEGORIES below), several at once; none for every job.
It answers 429 (too many requests) after about 12 requests in 2 seconds: one request every half second, and a
429 is tried once more after the wait it asks for.
"""

from __future__ import annotations

import html
import json
import re
import time

import httpx

from ..models import Job
from ..text import company_key, normalize, strip_html
from .base import Prefilter

# Groups that publish their companies' jobs under the group's name, the brand at the start of the title
# ("BM - Backend Developer"): the brand becomes the company, as on the company's own careers page.
GROUP_BRANDS = {"Grupo JPM": {"BM": "Balanças Marques", "Balanças Marques": "Balanças Marques", "SDILAB": "SDILAB"}}
_BRAND_RE = re.compile(r"^\s*([^|–-]{1,30}?)\s+[|–-]\s+(.+)$")


def _brand(company: str, title: str) -> tuple[str, str]:
    """(company, title) with a group's brand moved from the title to the company; anything else as it was."""
    def key(name):
        return company_key(name).replace(" ", "")
    brands = next(({key(b): name for b, name in by_brand.items()} for group, by_brand in GROUP_BRANDS.items()
                   if key(group) == key(company)), None)
    match = _BRAND_RE.match(title) if brands else None
    brand = brands.get(key(match.group(1))) if match else None
    return (brand, match.group(2).strip()) if brand else (company, title)

BASE = "https://emprego.sapo.pt"
_HTML = {"Accept": "text/html"}
DISTRICTS = {
    "aveiro", "beja", "braga", "braganca", "castelo-branco", "coimbra", "evora", "faro", "guarda", "leiria", "lisboa",
    "portalegre", "porto", "santarem", "setubal", "viana-do-castelo", "vila-real", "viseu", "ilha-da-madeira",
    "ilha-de-porto-santo", "ilha-de-santa-maria", "ilha-de-sao-miguel", "ilha-terceira", "ilha-graciosa",
    "ilha-de-sao-jorge", "ilha-do-pico", "ilha-do-faial", "ilha-das-flores", "ilha-do-corvo",
}
CATEGORIES = {
    "administrativo-secretariado", "agricultura-pescas", "ambiente", "apoio-domiciliario-e-limpezas", "arquitetura",
    "automovel", "banca-seguros", "beleza-estetica-bem-estar", "call-center-helpdesk-telemarketing", "comercial-vendas",
    "comunicacao-media-redes-sociais", "construcao-civil", "consultadoria-auditoria-assessoria",
    "contabilidade-fiscalidade-financas", "design-multimedia-artes-graficas", "desporto-fitness", "engenharia",
    "formacao-ensino-educacao", "gestao-economia", "grande-consumo-retail", "hotelaria-restauracao-turismo",
    "imobiliario", "industria-manutencao", "informatica-tecnologias", "juridico", "linguas-traducao",
    "logistica-compras-distribuicao", "marketing-publicidade-rp", "moda-confeccao-textil", "proprio-emprego",
    "qualidade", "recursos-humanos", "saude", "seguranca",
}
_LD_RE = re.compile(r'<script type="application/ld\+json">\s*(.*?)\s*</script>', re.S)


def districts(place_names: list[str]) -> list[str]:
    """The place names that are districts, as the search writes them: "Viana do Castelo" -> "viana-do-castelo"."""
    slugs = (normalize(name).replace(" ", "-") for name in place_names)
    return list(dict.fromkeys(slug for slug in slugs if slug in DISTRICTS))


def _prop(page: str, name: str):
    """A Vue attribute's JSON. Its value is in single quotes, so a quote inside is written &#039;."""
    match = re.search(rf":{re.escape(name)}='([^']*)'", page)
    return json.loads(html.unescape(match.group(1))) if match else None


def to_job(item: dict) -> Job:
    company = "" if item.get("anonymous") else item.get("company_name") or ""
    company, title = _brand(company or "Empresa confidencial", strip_html(item.get("offer_name")))
    return Job(
        source="sapo",
        external_id=str(item["id"]),
        company=company,
        title=title,
        location=item.get("location") or item.get("job_municipality") or item.get("job_district") or "",
        url=item.get("link") or f"{BASE}/offers/{item.get('canonical', '')}?id={item['id']}",
        posted_at=item.get("publication_date") or None,
        description=strip_html(item.get("job_description")),  # the start of it: the job's page has the rest
        contract=item.get("job_work_hours") or "",
        work_model="remote" if item.get("remote_work") else "",
    )


def parse_list(page: str) -> tuple[list[Job], int]:
    """The jobs of a results page and how many the search found in all."""
    offers = [item for item in _prop(page, "offers") or [] if item.get("offer_name")]  # not the ads among them
    return [to_job(item) for item in offers], int((_prop(page, "pagination") or {}).get("total") or 0)


def _posting(page: str) -> dict:
    for block in _LD_RE.findall(page):
        try:
            data = json.loads(block, strict=False)
        except ValueError:
            continue
        for item in data if isinstance(data, list) else [data]:
            if isinstance(item, dict) and item.get("@type") == "JobPosting":
                return item
    return {}


def _get(client: httpx.Client, url: str, params: dict | None = None, max_wait: float = 15.0) -> httpx.Response:
    resp = client.get(url, params=params, headers=_HTML)
    if resp.status_code == 429:  # too fast: wait as asked (or a few seconds), then once more
        try:
            wait = float(resp.headers.get("Retry-After", 5))
        except ValueError:
            wait = 5.0
        time.sleep(min(max(wait, 0.0), max_wait))
        resp = client.get(url, params=params, headers=_HTML)
    resp.raise_for_status()
    return resp


def _fill_detail(client: httpx.Client, job: Job) -> None:
    posting = _posting(_get(client, job.url).text)
    job.description = strip_html(posting.get("description")) or job.description
    logo = (posting.get("hiringOrganization") or {}).get("logo") or ""
    job.logo = logo if logo.startswith("http") else job.logo


def fetch(client: httpx.Client, entry: dict, prefilter: Prefilter = None, max_pages: int = 15,
          max_details: int = 30, pause: float = 0.5) -> list[Job]:
    places = entry.get("districts")
    if places is None:  # from the area in `search`: its place names that are districts
        places = districts(entry.get("location_names") or [])
    params = {}
    if places:
        params["local"] = ",".join(places)
    if entry.get("categories"):
        params["categoria"] = ",".join(entry["categories"])

    jobs: dict[str, Job] = {}
    for page in range(1, max_pages + 1):
        if page > 1:
            time.sleep(pause)
        found, total = parse_list(_get(client, f"{BASE}/offers", {**params, "pagina": page}).text)
        for job in found:
            jobs.setdefault(job.external_id, job)
        if not found or page * 9 >= total:
            break

    wanted = [job for job in jobs.values() if prefilter is None or prefilter(job)]
    for job in wanted[:max_details]:  # by title: no page for the jobs the filters cut anyway
        time.sleep(pause)
        try:
            _fill_detail(client, job)
        except httpx.HTTPError:
            pass  # keep the job with the start of its description
    return list(jobs.values())
