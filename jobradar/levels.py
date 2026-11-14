"""What you are looking for: the experience levels (👤 Profile → Level) and the job titles (roles).

  search.levels: any of internship, junior, mid, senior, lead; several are fine, and all of them is
                 any level. A job whose title (or its contract / level field) names only levels you
                 didn't pick is skipped; one naming a level you picked gets points.
  search.roles:  job titles you're after, e.g. "backend engineer". A title with every word of a role
                 is in your area, gets points, and is searched for on ITJobs.

Configs from before there were levels have no `levels`: they keep working exactly as they always did,
from search.junior_keywords (words that add points) and search.exclude_title_keywords (title words to
skip), which is Internship + Junior while that list has words, and any level when it is empty.
"""

from __future__ import annotations

import re

from .text import matched_terms, normalize

LEVELS = ("internship", "junior", "mid", "senior", "lead")
DEFAULT = ["internship", "junior"]  # what JobRadar always looked for

# The words that mark each level in a job title or its contract / level field, without accents.
# Senior + lead are the words JobRadar always skipped for juniors (search.exclude_title_keywords).
WORDS = {
    "internship": ["estagio", "estagiario", "estagiaria", "internship", "intern", "iefp"],
    "junior": ["junior", "jr", "trainee", "graduate", "entry level", "entry-level", "recem-licenciado",
               "recem licenciado", "academy"],
    "mid": ["mid", "intermediate", "intermedio", "pleno", "medior"],
    "senior": ["senior", "sr", "expert", "principal", "staff", "architect"],
    "lead": ["lead", "leader", "manager", "head", "director", "chief", "vp"],
}
# What to search for on job boards that take a search word (ITJobs), for each level
QUERIES = {
    "internship": ["estagio"],
    "junior": ["junior", "trainee", "graduate"],
    "mid": ["mid-level"],
    "senior": ["senior"],
    "lead": ["lead"],
}
# How many years a posting can ask before it's above the level (None: no limit). Internship and
# junior keep the limit JobRadar always had: 2 years cost a few points, 3 or more cost many.
YEARS_OK = {"internship": 1, "junior": 1, "mid": 4, "senior": None, "lead": None}
# For the AI: the scoring prompt is in English, the writing prompts in Portuguese
NAMES = {
    "en": {"internship": "internship", "junior": "junior", "mid": "mid-level", "senior": "senior",
           "lead": "lead / manager"},
    "pt": {"internship": "estágio", "junior": "júnior", "mid": "intermédio", "senior": "sénior",
           "lead": "liderança"},
}


def is_set(search: dict) -> bool:
    """True once levels were chosen (👤 Profile or config.yaml); until then the older lists decide."""
    return isinstance(search.get("levels"), list)


def canonical(levels) -> list[str]:
    """Known levels in LEVELS order, without repeats; none is the same as all of them (any level)."""
    picked = {normalize(str(level)).strip() for level in levels or []}
    return [level for level in LEVELS if level in picked] or list(LEVELS)


def unknown(levels) -> list[str]:
    return [str(level) for level in levels or [] if normalize(str(level)).strip() not in LEVELS]


def chosen(search: dict) -> list[str]:
    """The levels looked for. Older configs: Internship + Junior while they skip senior titles, else any."""
    if is_set(search):
        return canonical(search["levels"])
    return list(DEFAULT) if search.get("exclude_title_keywords") else list(LEVELS)


def any_level(levels: list[str]) -> bool:
    return set(LEVELS) <= set(levels)


def detect(text: str) -> dict[str, str]:
    """{level: the first of its words found} in already-normalised text."""
    found = {}
    for level in LEVELS:
        hits = matched_terms(text, WORDS[level])
        if hits:
            found[level] = hits[0]
    return found


def level_of(word: str) -> str | None:
    """The level a word marks ("lead" -> "lead", "estagio profissional" -> "internship"), or None."""
    return next(iter(detect(normalize(word))), None)


def extra_words(words: list[str]) -> list[str]:
    """The words of a list that are not level words: with levels chosen, only these still count."""
    return [w for w in words or [] if not detect(normalize(str(w)))]


def wanted_words(search: dict) -> list[str]:
    """Words that mark a level looked for (they add points)."""
    if not is_set(search):
        return list(search.get("junior_keywords") or [])
    levels = chosen(search)
    own = [] if any_level(levels) else [w for level in levels for w in WORDS[level]]
    return own + extra_words(search.get("junior_keywords") or [])


def skipped_title_words(search: dict) -> list[str]:
    """Words of exclude_title_keywords that still skip a title: all of them until levels are chosen,
    then only the ones that aren't level words (the levels decide those)."""
    words = list(search.get("exclude_title_keywords") or [])
    return extra_words(words) if is_set(search) else words


def level_text(title: str, meta: str) -> str:
    """The text that says a job's level, both already normalised: the title when it names one, else the
    site's contract / level field. "(Senior) Backend Developer" is senior even where the site files it
    under "Mid-Senior Level"."""
    return title if detect(title) else meta


def other_level(title: str, meta: str, search: dict) -> str | None:
    """With levels chosen: the word of another level, when the job's level text (level_text) names levels
    and none of them is one looked for ("Senior/Lead" stays for a senior; "Junior" goes). None: it may stay."""
    if not is_set(search):
        return None
    levels = chosen(search)
    if any_level(levels):
        return None
    found = detect(level_text(title, meta))
    if not found or set(found) & set(levels):
        return None
    return next(iter(found.values()))


def years_ok(search: dict) -> int | None:
    """The most years a posting can ask for the levels looked for (None: no limit)."""
    limits = [YEARS_OK[level] for level in chosen(search)]
    return None if None in limits else max(limits)


def queries(search: dict) -> list[str]:
    """What to search for on a job board that takes a search word: the levels' words and the roles."""
    levels = chosen(search)
    words = [] if any_level(levels) else [q for level in levels for q in QUERIES[level]]
    unique: dict[str, str] = {}
    for word in words + [str(role) for role in search.get("roles") or []]:
        unique.setdefault(normalize(word), word)
    return list(unique.values())


# Roles are compared word by word, with "back-end" read as "backend"
_HYPHEN = re.compile(r"(?<=[a-z0-9])-(?=[a-z0-9])")
_WORD = re.compile(r"[a-z0-9#+]+")


def _tokens(text: str) -> list[str]:
    return _WORD.findall(_HYPHEN.sub("", normalize(text)))


def matched_roles(title: str, roles: list[str]) -> list[str]:
    """The roles whose every word is in the title: "Backend Engineer" in "Senior Backend Engineer (Python)"."""
    words = set(_tokens(title))
    return [role for role in roles or [] if _tokens(role) and set(_tokens(role)) <= words]


def without_roles(title: str, roles: list[str]) -> str:
    """The normalised title without the words of the roles it has, so a role such as "Product Manager"
    or "Tech Lead" is not read as a level. With no roles, just the normalised title."""
    text = normalize(title)
    for role in matched_roles(text, roles):
        for word in _tokens(role):
            text = re.sub(r"(?<![a-z0-9])" + re.escape(word) + r"(?![a-z0-9#+])", " ", text)
    return text


def for_ai(search: dict, language: str = "en") -> str:
    """The levels and roles looked for, as lines for the AI's prompts. Empty until they are chosen,
    so the prompts stay exactly as they were for anyone who hasn't changed them."""
    roles = list(search.get("roles") or [])
    if not is_set(search) and not roles:
        return ""
    levels = chosen(search)
    names = NAMES[language]
    if language == "pt":
        level = "qualquer nível" if any_level(levels) else ", ".join(names[lv] for lv in levels)
        lines = [f"Nível procurado: {level}"] + ([f"Funções procuradas: {', '.join(roles)}"] if roles else [])
    else:
        level = "any level" if any_level(levels) else ", ".join(names[lv] for lv in levels)
        lines = [f"Experience level wanted: {level}"] + ([f"Target roles: {', '.join(roles)}"] if roles else [])
    return "\n".join(lines)
