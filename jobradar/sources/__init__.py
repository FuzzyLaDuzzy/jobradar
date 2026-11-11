"""Source connectors. Each `fetch(client, entry, prefilter)` returns a list of Jobs."""

from . import (balancasmarques, bamboohr, eurotux, greenhouse, iefp, itjobs, landingjobs, lever, netempregos, randstad, recruitee, smartrecruiters,
               successfactors, sysmatch, teamtailor, workable, workday, workinbraga, zohorecruit)
from .base import SourceSkipped, make_client

FETCHERS = {
    "smartrecruiters": smartrecruiters.fetch,
    "smartrecruiters_search": smartrecruiters.search,
    "lever": lever.fetch,
    "workday": workday.fetch,
    "successfactors": successfactors.fetch,
    "bamboohr": bamboohr.fetch,
    "recruitee": recruitee.fetch,
    "zohorecruit": zohorecruit.fetch,
    "teamtailor": teamtailor.fetch,
    "greenhouse": greenhouse.fetch,
    "itjobs": itjobs.fetch,
    "landingjobs": landingjobs.fetch,
    "netempregos": netempregos.fetch,
    "randstad": randstad.fetch,
    "sysmatch": sysmatch.fetch,
    "eurotux": eurotux.fetch,
    "balancasmarques": balancasmarques.fetch,
    "workable": workable.fetch,
    "workinbraga": workinbraga.fetch,
    "iefp": iefp.fetch,
}

# Which config field names each entry (used in the source label).
LABEL_FIELD = {
    "smartrecruiters": "company",
    "smartrecruiters_search": None,
    "lever": "site",
    "workday": "name",
    "successfactors": "name",
    "bamboohr": "name",
    "recruitee": "company",
    "zohorecruit": "name",
    "teamtailor": "company",
    "greenhouse": "company",
    "itjobs": None,
    "landingjobs": None,
    "netempregos": None,
    "randstad": None,
    "sysmatch": None,
    "eurotux": None,
    "balancasmarques": None,
    "workable": None,
    "workinbraga": None,
    "iefp": None,
}

REQUIRED_FIELDS = {
    "smartrecruiters": ["company"],
    "smartrecruiters_search": [],
    "lever": ["site"],
    "workday": ["url"],
    "successfactors": ["name", "url"],
    "bamboohr": ["name", "site"],
    "recruitee": ["company"],
    "zohorecruit": ["name", "url"],
    "teamtailor": ["company"],
    "greenhouse": ["company"],
    "itjobs": [],
    "landingjobs": [],
    "netempregos": [],
    "randstad": [],
    "sysmatch": [],
    "eurotux": [],
    "balancasmarques": [],
    "workable": [],
    "workinbraga": [],
    "iefp": [],
}


def with_area(kind: str, entry: dict, search: dict, sources: dict | None = None) -> dict:
    """The area is written once, in `search`: sources that search by place use it,
    unless the entry names its own (`search`, `location` or ITJobs `locations`).
    `sources` (the config's): the SmartRecruiters search leaves out the companies followed on their own."""
    places = search.get("locations_primary") or (search.get("locations") or [])[:1]
    defaults = {
        "workday": {"search": places},
        "successfactors": {"location": places},
        "workable": {"location": places},
        "iefp": {"location": places},
        "smartrecruiters_search": {"keyword": places,
                                   "skip": [e.get("company", "") for e in (sources or {}).get("smartrecruiters") or []]},
        "itjobs": {"location_names": search.get("locations") or []},
    }
    return {**defaults.get(kind, {}), **entry}


def source_label(kind: str, entry: dict) -> str:
    field = LABEL_FIELD.get(kind)
    if field is None:
        return kind
    value = entry.get(field)
    if kind == "workday" and not value:
        value = workday.parse_board(entry["url"], entry.get("tenant"))[2]
    return f"{kind}:{value}"


__all__ = ["FETCHERS", "REQUIRED_FIELDS", "SourceSkipped", "make_client", "source_label", "with_area"]
