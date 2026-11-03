"""Source connectors. Each `fetch(client, entry, prefilter)` returns a list of Jobs."""

from . import (balancasmarques, bamboohr, eurotux, itjobs, landingjobs, lever, netempregos, randstad, recruitee, smartrecruiters,
               successfactors, sysmatch, teamtailor, workday, zohorecruit)
from .base import SourceSkipped, make_client

FETCHERS = {
    "smartrecruiters": smartrecruiters.fetch,
    "lever": lever.fetch,
    "workday": workday.fetch,
    "successfactors": successfactors.fetch,
    "bamboohr": bamboohr.fetch,
    "recruitee": recruitee.fetch,
    "zohorecruit": zohorecruit.fetch,
    "teamtailor": teamtailor.fetch,
    "itjobs": itjobs.fetch,
    "landingjobs": landingjobs.fetch,
    "netempregos": netempregos.fetch,
    "randstad": randstad.fetch,
    "sysmatch": sysmatch.fetch,
    "eurotux": eurotux.fetch,
    "balancasmarques": balancasmarques.fetch,
}

# Which config field names each entry (used in the source label).
LABEL_FIELD = {
    "smartrecruiters": "company",
    "lever": "site",
    "workday": "name",
    "successfactors": "name",
    "bamboohr": "name",
    "recruitee": "company",
    "zohorecruit": "name",
    "teamtailor": "company",
    "itjobs": None,
    "landingjobs": None,
    "netempregos": None,
    "randstad": None,
    "sysmatch": None,
    "eurotux": None,
    "balancasmarques": None,
}

REQUIRED_FIELDS = {
    "smartrecruiters": ["company"],
    "lever": ["site"],
    "workday": ["url"],
    "successfactors": ["name", "url"],
    "bamboohr": ["name", "site"],
    "recruitee": ["company"],
    "zohorecruit": ["name", "url"],
    "teamtailor": ["company"],
    "itjobs": [],
    "landingjobs": [],
    "netempregos": [],
    "randstad": [],
    "sysmatch": [],
    "eurotux": [],
    "balancasmarques": [],
}


def with_area(kind: str, entry: dict, search: dict) -> dict:
    """The area is written once, in `search`: sources that search by place use it,
    unless the entry names its own (`search`, `location` or ITJobs `locations`)."""
    places = search.get("locations_primary") or (search.get("locations") or [])[:1]
    defaults = {
        "workday": {"search": places},
        "successfactors": {"location": places},
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
