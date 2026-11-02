"""ITJobs.pt official API (Portugal's main IT job board).

Needs a free read-only API key: request it at https://www.itjobs.pt/api and put it
in the .env file as ITJOBS_API_KEY.
  GET https://api.itjobs.pt/job/search.json?api_key=...&q=junior&limit=100&page=1
  GET https://api.itjobs.pt/job/list.json?api_key=...&contract=3   (3 = estágio profissional)
  GET https://api.itjobs.pt/job/list.json?api_key=...&location=4   (4 = Braga district)
  GET https://api.itjobs.pt/location/list.json?api_key=...          (district ids by name)
"""

from __future__ import annotations

import os

import httpx

from ..models import Job
from ..i18n import t
from ..text import normalize, strip_html
from .base import Prefilter, SourceSkipped

API = "https://api.itjobs.pt/{method}.json"
PROFESSIONAL_INTERNSHIP = 3
WORK_MODELS = {0: "on-site", 1: "remote", 2: "hybrid"}
# The API names contracts in English ("Internship", "Academic"), but the filters use
# the Portuguese names from the docs.
CONTRACT_NAMES = {str(PROFESSIONAL_INTERNSHIP): "Estágio profissional", "5": "Estágio académico"}


def to_job(item: dict) -> Job:
    company = item.get("company") or {}
    pairs = [(str(c.get("id")), c.get("name", "")) for c in item.get("contracts") or []]
    if len(pairs) > 1:  # academic among other options: not an academic-only job
        pairs = [p for p in pairs if p[0] != "5"]
    contracts = [CONTRACT_NAMES.get(cid, name) for cid, name in pairs]
    types = [t.get("name", "") for t in item.get("types") or []]
    try:
        work_model = WORK_MODELS.get(int(item.get("workModel", -1)), "")
    except (TypeError, ValueError):
        work_model = ""
    return Job(
        source="itjobs",
        external_id=str(item["id"]),
        company=company.get("name") or "",
        title=(item.get("title") or "").strip(),
        location=", ".join(loc.get("name", "") for loc in item.get("locations") or []),
        url=f"https://www.itjobs.pt/oferta/{item['id']}/{item.get('slug', '')}".rstrip("/"),
        posted_at=(item.get("publishedAt") or "")[:10] or None,
        description=strip_html(item.get("body")),
        contract=", ".join(c for c in contracts + types if c),
        work_model=work_model,
        logo=company.get("logo") or "",
    )


def _error(data) -> str | None:
    if isinstance(data, dict) and data.get("error"):
        return str(data["error"].get("message", "error"))
    return None


def _json(resp: httpx.Response):
    # Not raise_for_status(): its message has the URL, and the GET URL has the api_key.
    if resp.is_error:
        raise RuntimeError(f"ITJobs: HTTP {resp.status_code}")
    return resp.json()


def _call(client: httpx.Client, method: str, params: dict) -> dict:
    """The docs say GET, but every example sends the fields as a POST form, so
    if GET is refused because of the key, the same call is retried as POST."""
    url = API.format(method=method)
    data = _json(client.get(url, params=params))
    message = _error(data)
    if message and "key" in message.lower():
        data = _json(client.post(url, data=params))
        message = _error(data)
        if message and "key" in message.lower():
            raise RuntimeError(t(
                "ITJobs: {message}. Confirma a chave no .env (ITJOBS_API_KEY=..., sem espaços "
                "nem aspas) e que é a que recebeste por email de itjobs.pt/api.", message=message))
    if message:
        raise RuntimeError(f"ITJobs: {message}")
    return data


def district_ids(client: httpx.Client, api_key: str, names: list[str]) -> list[int]:
    wanted = {normalize(n) for n in names}
    data = _call(client, "location/list", {"api_key": api_key, "limit": 50})
    return [loc["id"] for loc in data.get("results") or [] if normalize(loc.get("name")) in wanted]


def fetch(
    client: httpx.Client,
    entry: dict,
    prefilter: Prefilter = None,
    api_key: str | None = None,
) -> list[Job]:
    api_key = api_key or os.environ.get("ITJOBS_API_KEY")
    if not api_key:
        raise SourceSkipped(t("Falta ITJOBS_API_KEY no .env (pede-a grátis em itjobs.pt/api)"))

    max_pages = int(entry.get("max_pages", 2))
    requests: list[tuple[str, dict]] = [
        ("job/search", {"q": q}) for q in entry.get("queries") or []
    ]
    if entry.get("professional_internships", True):
        requests.append(("job/list", {"contract": PROFESSIONAL_INTERNSHIP}))
    # every job in these districts, not only the ones matching a query: the entry's own ids
    # (4 = Braga), or the districts named in search.locations
    districts = entry.get("locations")
    if districts is None and entry.get("location_names"):
        districts = district_ids(client, api_key, entry["location_names"])
    requests += [("job/list", {"location": loc}) for loc in districts or []]

    found: dict[str, Job] = {}
    for method, extra in requests:
        for page in range(1, max_pages + 1):
            data = _call(
                client, method, {"api_key": api_key, "limit": 100, "page": page, **extra}
            )
            results = data.get("results") or []
            for item in results:
                job = to_job(item)
                found.setdefault(job.uid, job)
            if len(results) < 100:
                break
    return list(found.values())
