"""How well a job fits the profile, from 0 to 100.

The keyword score always runs. If scoring.llm is enabled and the provider's key is
set (GEMINI_API_KEY or ANTHROPIC_API_KEY), new jobs also get an LLM score with a
one-line reason; the final score then mixes both (40% keywords, 60% LLM).
"""

from __future__ import annotations

import importlib.util
import json
import os
import re

from . import gemini, i18n, levels
from .models import Job
from .text import matched_terms, normalize

# provider: (key in .env, model that scores every job, model that writes application messages)
PROVIDERS = {
    "gemini": ("GEMINI_API_KEY", "gemini-3.5-flash-lite", "gemini-3.5-flash-lite"),  # free tier
    "anthropic": ("ANTHROPIC_API_KEY", "claude-haiku-5-5", "claude-opus-5-5"),
}
# ⚙ the AI model: Google's own list (gemini.list_models), else these; one Gemini model scores and writes
GEMINI_MODELS = ["gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-3.8-flash", "gemini-2.5-flash-lite", "gemini-2.5-flash"]
_VARIANTS = ("flash-lite", "flash", "pro")


def _gemini_order(model: str) -> tuple:
    """Newest version first; within one, Flash Lite, Flash, Pro; previews after."""
    match = gemini.MODEL_RE.match(model)
    major, minor = (match.group(1) + ".0").split(".")[:2]  # "3" is 3.0, older than 3.8
    return (-int(major), -int(minor)), _VARIANTS.index(match.group(2)), bool(match.group(3))


def ai_choice(choice: str) -> dict | None:
    """One ⚙ choice: "gemini:<model>" (any Gemini text model, as Google names them) or "anthropic"."""
    if choice == "anthropic":
        _, model, writes = PROVIDERS["anthropic"]
        return {"id": "anthropic", "provider": "anthropic", "model": model, "message_model": writes,
                "label": i18n.t("Claude: Haiku 5.5 avalia, Opus 5.5 escreve"), "default": False}
    provider, _, model = choice.partition(":")
    if provider != "gemini" or not gemini.MODEL_RE.match(model):
        return None
    words = model.removeprefix("gemini-").replace("-preview", "").split("-")
    label = "Gemini " + " ".join(w.capitalize() for w in words) + (" (preview)" if model.endswith("-preview") else "")
    return {"id": choice, "provider": "gemini", "model": model, "message_model": model, "label": label,
            "default": model == PROVIDERS["gemini"][1]}


def ai_choices(gemini_models: list[str]) -> list[dict]:
    models = sorted({m for m in gemini_models if gemini.MODEL_RE.match(m)} | {PROVIDERS["gemini"][1]}, key=_gemini_order)
    # Claude only where its package is installed (not in the phone app)
    claude = [ai_choice("anthropic")] if importlib.util.find_spec("anthropic") else []
    return [ai_choice(f"gemini:{m}") for m in models] + claude


def current_choice(cfg: dict) -> str:
    settings = llm_settings(cfg)
    return "anthropic" if settings["provider"] == "anthropic" else f"gemini:{settings['model']}"


def llm_settings(cfg: dict) -> dict:
    llm = ((cfg.get("scoring") or {}).get("llm")) or {}
    provider = llm.get("provider", "anthropic")
    key_env, model, message_model = PROVIDERS[provider]
    return {"enabled": bool(llm.get("enabled")), "provider": provider, "key_env": key_env,
            "model": llm.get("model") or model, "message_model": llm.get("message_model") or message_model}


def keyword_score(job: Job, cfg: dict, flags: dict | None = None) -> tuple[int, list[str]]:
    profile = cfg.get("profile") or {}
    search = cfg.get("search") or {}
    flags = flags or {}
    text = normalize(job.full_text())
    title_meta = normalize(" ".join([job.title, job.experience, job.contract]))
    reasons: list[str] = []
    score = 0
    roles = search.get("roles") or []
    chosen = levels.is_set(search)  # False: the config from before levels, scored as it always was
    wanted = levels.chosen(search)

    if chosen:
        # the title's level when it names one, else the site's field (as the filter reads it); the words
        # of a role you're after ("Tech Lead") don't count as a level
        level = levels.level_text(levels.without_roles(job.title, roles),
                                  normalize(" ".join([job.experience, job.contract])))
        if matched_terms(level, levels.wanted_words(search)):
            score += 25
            reasons.append("nível pretendido")
    elif matched_terms(title_meta, search.get("junior_keywords") or []):
        score += 25
        reasons.append("júnior/estágio")
    internships = not chosen or ("internship" in wanted and not levels.any_level(wanted))
    if internships and ("estagio profissional" in title_meta or "iefp" in text):
        score += 10
        reasons.append("estágio profissional")
    if levels.matched_roles(job.title, roles):
        score += 20
        reasons.append("função pretendida")

    loc = normalize(job.location)
    if matched_terms(loc, search.get("locations_primary") or []):
        score += 15
        reasons.append("zona preferida")  # stored in Portuguese, translated by the UI
    elif matched_terms(loc, search.get("locations") or []):
        score += 8

    skills = matched_terms(text, profile.get("skills") or [])
    score += min(36, 6 * len(skills))
    focus = matched_terms(text, profile.get("focus") or [])
    score += min(24, 8 * len(focus))
    stack = list(dict.fromkeys(focus + skills))[:5]
    if stack:
        reasons.append(", ".join(stack))

    # The UI already shows a "Pede N+ anos" badge, so this only adjusts the score. Up to the years
    # your levels allow is fine, one more costs a little, more than that a lot (junior: 2 and 3+).
    years = flags.get("years_required")
    allowed = 1 if not chosen else levels.years_ok(search)
    if years and allowed is not None:
        if years >= allowed + 2:
            score -= 20
        elif years == allowed + 1:
            score -= 5
    # e.g. SmartRecruiters "Mid-Senior Level"; with levels chosen, the filter already read that field
    if not chosen and "senior" in normalize(job.experience):
        score -= 10

    return max(0, min(100, score)), reasons


PROMPT = """You are helping a candidate decide which job postings to apply to.

Candidate profile:
{profile}

{wanted}{decisions}Job posting:
Title: {title}
Company: {company}
Location: {location}
Contract / level: {meta}
Description:
{description}

Rate from 0 to 100 how good a fit this job is for the candidate, considering the seniority
they are looking for (see the profile), the required skills, the location and, when there are
any, the candidate's own choices above. Reply with
JSON only, like {{"score": 72, "reason": "{reason}"}}."""
REASON = {"pt": "uma frase curta em português europeu", "en": "one short sentence in English"}


def decisions_text(examples: dict | None) -> str:
    """The candidate's own choices as examples for the score: jobs applied to or saved, and jobs discarded.
    Titles come from job sites: one short line each, read as data like the posting."""
    def lines(items):
        return "\n".join("- " + " ".join(str(item).split())[:120] for item in items)

    parts = []
    if (examples or {}).get("liked"):
        parts.append("Jobs the candidate applied to or saved (more like these):\n" + lines(examples["liked"]))
    if (examples or {}).get("disliked"):
        parts.append("Jobs the candidate discarded (fewer like these):\n" + lines(examples["disliked"]))
    return "\n\n".join(parts) + "\n\n" if parts else ""


def _parse_llm_reply(text: str) -> tuple[int, str] | None:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
        score = int(data["score"])
        return max(0, min(100, score)), str(data.get("reason", "")).strip()
    except (ValueError, KeyError, TypeError):
        return None


def llm_available(cfg: dict) -> bool:
    settings = llm_settings(cfg)
    return settings["enabled"] and bool(os.environ.get(settings["key_env"]))


def llm_score(job: Job, cfg: dict, client=None, examples: dict | None = None) -> tuple[int, str] | None:
    """examples: {"liked": [...], "disliked": [...]}, the candidate's past choices (Database.decision_examples)."""
    settings = llm_settings(cfg)
    wanted = levels.for_ai(cfg.get("search") or {})  # "" until levels or roles are chosen: the prompt as it was
    prompt = PROMPT.format(
        profile=(cfg.get("profile") or {}).get("cv_summary", ""),
        wanted=f"What the candidate is looking for:\n{wanted}\n\n" if wanted else "",
        decisions=decisions_text(examples),
        title=job.title,
        company=job.company,
        location=job.location,
        meta=", ".join(x for x in [job.contract, job.experience, job.work_model] if x),
        description=(job.description or "(sem descrição)")[:6000],
        reason=REASON[i18n.language],
    )
    if settings["provider"] == "gemini":
        return _parse_llm_reply(gemini.generate(prompt, settings["model"], max_tokens=2000, client=client))
    if client is None:
        import anthropic

        client = anthropic.Anthropic()
    message = client.messages.create(
        model=settings["model"],
        # Haiku 5.5 thinks by default and thinking counts against max_tokens: leave room for the JSON
        max_tokens=2000,
        output_config={"effort": "low"},  # a short classification needs little reasoning
        messages=[{"role": "user", "content": prompt}],
    )
    reply = "".join(getattr(block, "text", "") for block in message.content)
    return _parse_llm_reply(reply)


def combine(kw: int, llm: int | None) -> int:
    if llm is None:
        return kw
    return round(0.4 * kw + 0.6 * llm)
