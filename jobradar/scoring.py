"""How well a job fits the profile, from 0 to 100.

The keyword score always runs. If scoring.llm is enabled and the provider's key is
set (GEMINI_API_KEY or ANTHROPIC_API_KEY), new jobs also get an LLM score with a
one-line reason; the final score then mixes both (40% keywords, 60% LLM).
"""

from __future__ import annotations

import json
import os
import re

from . import gemini, i18n
from .models import Job
from .text import matched_terms, normalize

# provider: (key in .env, model that scores every job, model that writes application messages)
PROVIDERS = {
    "gemini": ("GEMINI_API_KEY", "gemini-3.5-flash-lite", "gemini-3.8-flash"),  # free tier
    "anthropic": ("ANTHROPIC_API_KEY", "claude-haiku-5-5", "claude-opus-5-5"),
}


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

    junior = matched_terms(title_meta, search.get("junior_keywords") or [])
    if junior:
        score += 25
        reasons.append("júnior/estágio")
    if "estagio profissional" in title_meta or "iefp" in text:
        score += 10
        reasons.append("estágio profissional")

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

    # The UI already shows a "Pede N+ anos" badge, so this only adjusts the score.
    years = flags.get("years_required")
    if years and years >= 3:
        score -= 20
    elif years == 2:
        score -= 5
    if "senior" in normalize(job.experience):  # e.g. SmartRecruiters "Mid-Senior Level"
        score -= 10

    return max(0, min(100, score)), reasons


PROMPT = """You are helping a candidate decide which job postings to apply to.

Candidate profile:
{profile}

Job posting:
Title: {title}
Company: {company}
Location: {location}
Contract / level: {meta}
Description:
{description}

Rate from 0 to 100 how good a fit this job is for the candidate, considering the seniority
they are looking for (see the profile), the required skills and the location. Reply with
JSON only, like {{"score": 72, "reason": "{reason}"}}."""
REASON = {"pt": "uma frase curta em português europeu", "en": "one short sentence in English"}


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


def llm_score(job: Job, cfg: dict, client=None) -> tuple[int, str] | None:
    settings = llm_settings(cfg)
    prompt = PROMPT.format(
        profile=(cfg.get("profile") or {}).get("cv_summary", ""),
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
