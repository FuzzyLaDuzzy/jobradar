"""Decide which jobs to keep. Two stages:

* quick_reject: uses only list data (title, company, location), so sources can
  skip the extra request for the description of jobs we will drop anyway.
* evaluate: the full check, run after descriptions are loaded.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from .models import Job
from .text import contains_term, matched_terms, normalize

_MULTI_LOCATION = re.compile(r"^\d+\s+(locations|localizacoes|locais)$")
_REMOTE_WORDS = ["remote", "remoto", "teletrabalho"]
_PORTUGAL_WORDS = ["portugal", "pt"]
# Places outside the chosen area, used only when a job has no location field.
# Main Portuguese cities only: a job naming a smaller town stays "unknown".
_OTHER_PLACES = ["porto", "lisboa", "lisbon", "aveiro", "coimbra", "leiria", "setubal", "faro", "viseu",
                 "evora", "maia", "matosinhos", "gaia", "oeiras", "sintra", "amadora", "cascais", "almada"]

_YEARS_PATTERNS = [
    # "3+ years of experience", "2-4 years of professional experience", "3 anos de experiência"
    re.compile(
        r"(\d{1,2})\s*\+?\s*(?:-|to|a)?\s*\d{0,2}\s*\+?\s*(?:years?|anos)\s+(?:of\s+|de\s+)?"
        r"(?:[a-z\-]+\s+){0,3}?(?:experience|experiencia)"
    ),
    # "experience: 2+ years", "experiência mínima de 3 anos"
    re.compile(r"(?:experience|experiencia)[^.\n]{0,40}?(\d{1,2})\s*\+?\s*(?:years?|anos)"),
]


def location_status(job: Job, search: dict) -> bool | None:
    """True = in an accepted area, False = outside, None = unknown."""
    loc = normalize(job.location).strip()
    if not loc or _MULTI_LOCATION.match(loc):
        # ITJobs sends remote jobs with no location at all
        if job.work_model == "remote" and not search.get("allow_remote"):
            return False
        # ITJobs and Sysmatch often name the city only in the text
        text = normalize(f"{job.title}\n{job.description}")
        if matched_terms(text, search.get("locations") or []):
            return True
        if matched_terms(text, _OTHER_PLACES):
            return False
        return None
    if matched_terms(loc, search.get("locations") or []):
        return True
    if search.get("allow_remote"):
        is_remote = job.work_model == "remote" or bool(matched_terms(loc, _REMOTE_WORDS))
        if is_remote and (matched_terms(loc, _PORTUGAL_WORDS) or job.source == "itjobs"):
            return True
    return False


def quick_reject(job: Job, search: dict) -> str | None:
    company = normalize(job.company)
    for name in search.get("exclude_companies") or []:
        if normalize(name) and normalize(name) in company:
            return f"empresa excluída ({name})"
    title = normalize(job.title)
    hits = matched_terms(title, search.get("exclude_title_keywords") or [])
    if hits:
        return f"título sénior ({hits[0]})"
    hits = matched_terms(title, search.get("exclude_keywords") or [])
    if hits:
        return f"excluída ({hits[0]})"
    kind_terms = search.get("title_keywords") or []
    if kind_terms and not matched_terms(title, kind_terms):
        return "fora da área"
    if location_status(job, search) is False:
        return "fora da zona"
    return None


def years_required(job: Job) -> int | None:
    text = normalize(job.description)
    found = []
    for pattern in _YEARS_PATTERNS:
        for match in pattern.finditer(text):
            years = int(match.group(1))
            if 0 < years <= 15:
                found.append(years)
    return min(found) if found else None


def evaluate(job: Job, search: dict, today: date | None = None) -> tuple[bool, str | None, dict]:
    """Return (keep, reason_if_dropped, flags)."""
    reason = quick_reject(job, search)
    if reason:
        return False, reason, {}

    meta = normalize(" ".join([job.contract, job.experience]))
    hits = matched_terms(meta, search.get("exclude_keywords") or [])
    if hits:
        return False, f"excluída ({hits[0]})", {}

    text = normalize(job.full_text())
    scam = [w for w in search.get("scam_keywords") or [] if contains_term(text, w)]
    if scam:
        return False, f"suspeita de burla ({scam[0]})", {}

    max_age = search.get("max_age_days")
    if max_age and job.posted_at:
        today = today or date.today()
        try:
            if date.fromisoformat(job.posted_at) < today - timedelta(days=int(max_age)):
                return False, "antiga", {}
        except ValueError:
            pass

    flags: dict = {}
    if location_status(job, search) is None:
        flags["location_unknown"] = True
    years = years_required(job)
    if years:
        flags["years_required"] = years
    return True, None, flags
