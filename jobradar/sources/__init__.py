"""Source connectors. Each `fetch(client, entry, prefilter)` returns a list of Jobs."""

from . import (bamboohr, itjobs, landingjobs, lever, netempregos, randstad, smartrecruiters, successfactors, sysmatch,
               workday)
from .base import SourceSkipped, make_client

FETCHERS = {
    "smartrecruiters": smartrecruiters.fetch,
    "lever": lever.fetch,
    "workday": workday.fetch,
    "successfactors": successfactors.fetch,
    "bamboohr": bamboohr.fetch,
    "itjobs": itjobs.fetch,
    "landingjobs": landingjobs.fetch,
    "netempregos": netempregos.fetch,
    "randstad": randstad.fetch,
    "sysmatch": sysmatch.fetch,
}

# Which config field names each entry (used in the source label).
LABEL_FIELD = {
    "smartrecruiters": "company",
    "lever": "site",
    "workday": "name",
    "successfactors": "name",
    "bamboohr": "name",
    "itjobs": None,
    "landingjobs": None,
    "netempregos": None,
    "randstad": None,
    "sysmatch": None,
}

REQUIRED_FIELDS = {
    "smartrecruiters": ["company"],
    "lever": ["site"],
    "workday": ["url"],
    "successfactors": ["name", "url"],
    "bamboohr": ["name", "site"],
    "itjobs": [],
    "landingjobs": [],
    "netempregos": [],
    "randstad": [],
    "sysmatch": [],
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
