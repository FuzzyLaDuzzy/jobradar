"""Decide which jobs to keep. Two stages:

* quick_reject: uses only list data (title, company, location), so sources can
  skip the extra request for the description of jobs we will drop anyway.
* evaluate: the full check, run after descriptions are loaded.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from .i18n import t
from .models import Job
from .text import contains_term, matched_terms, normalize

_MULTI_LOCATION = re.compile(r"^\d+\s+(locations|localizacoes|locais)$")
_REMOTE_WORDS = ["remote", "remoto", "teletrabalho"]
_PORTUGAL_WORDS = ["portugal", "pt"]
# Places outside the chosen area: in the title, or in the text when a job has no location field.
# Main Portuguese cities only: a job naming a smaller town stays "unknown". Whichever of them is
# in the chosen area counts as in it ("guarda" is left out: in Portuguese it is also a common verb).
_OTHER_PLACES = ["porto", "lisboa", "lisbon", "braga", "aveiro", "coimbra", "leiria", "setubal", "faro", "viseu",
                 "evora", "guimaraes", "braganca", "vila real", "viana do castelo", "castelo branco", "covilha",
                 "santarem", "beja", "portalegre", "funchal", "ponta delgada",
                 "maia", "matosinhos", "gaia", "oeiras", "sintra", "amadora", "cascais", "almada"]
# A title that sends the job abroad: "Relocate to Greece", "Work Remotely from Greece", "based in Athens"
_ELSEWHERE_RE = re.compile(r"\b(?:relocat\w*|based in|work(?:ing)?(?: remotely)? from (?!home\b))")


def _title_elsewhere(title: str, search: dict) -> bool:
    """The title puts the job somewhere else ("Engineer - Lisbon Based"), whatever the location field says."""
    if matched_terms(title, search.get("locations") or []):
        return False  # "Porto or Braga": the area is one of the places
    return bool(matched_terms(title, _OTHER_PLACES) or _ELSEWHERE_RE.search(title))

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
    if _title_elsewhere(normalize(job.title), search):
        return False
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


def reason_label(reason: str) -> str:
    """A reason for cutting a job, in the app's language: "título sénior (lead)" -> "senior title (lead)"."""
    names = {"título sénior": t("título sénior"), "excluída": t("excluída"), "fora da área": t("fora da área"),
             "fora da zona": t("fora da zona"), "antiga": t("antiga"), "suspeita de burla": t("suspeita de burla"),
             "empresa excluída": t("empresa excluída")}
    name, _, rest = reason.partition(" (")
    return names.get(name, name) + (f" ({rest}" if rest else "")
