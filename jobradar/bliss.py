"""Bliss, JobRadar's assistant: one AI call per message, with a summary of your data.

The AI answers in JSON (a text, the jobs to show and at most one proposed action); app.js shows the
action with a Confirm button and runs it through the routes that already exist. Nothing changes on its own.
"""

from __future__ import annotations

from . import i18n, levels, profile, salary
from .db import STATUSES, Database
from .text import normalize

# What Bliss knows about the app and the person who made it: only public facts (no email, no phone)
ABOUT = """O JobRadar é uma app livre e gratuita para procurar emprego, para Android, Windows, macOS e Linux
(github.com/FuzzyLaDuzzy/jobradar). Lê os sites de emprego e os sites de carreiras das empresas da zona da
pessoa, corta o que não serve (zona, nível, área, exclusões, burlas, vagas antigas) e mostra o que cortou e
porquê no separador ✂ Cortadas. Dá a cada vaga uma pontuação de encaixe com o perfil (palavras-chave e,
com uma chave de IA, uma avaliação da IA). Guarda o estado de cada candidatura (nova, guardada, candidatei,
entrevista, oferta, rejeitada, descartada), lembra o seguimento ao fim de 7 dias e escreve mensagens de
candidatura. Tem a ⚡ Triagem rápida (as vagas novas uma a uma), o 📊 Mercado (as competências mais pedidas),
o 👤 Perfil (lido do CV) e funciona em português e em inglês.

Foi criado por Flávio Silva, que fez o mestrado (MSc) em Engenharia Informática na Universidade do Minho,
com uma tese sobre qualidade de dados. Também criou o dqvouch (github.com/FuzzyLaDuzzy/dqvouch), uma
ferramenta livre que propõe testes de qualidade de dados. Portefólio: fuzzyladuzzy.github.io.
LinkedIn: linkedin.com/in/flávio-alex-silva. GitHub: github.com/FuzzyLaDuzzy."""

MAX_DESCRIPTION = 6000
MAX_CUT = 10


def _words(text: str) -> set[str]:
    return {w for w in "".join(c if c.isalnum() else " " for c in normalize(text)).split() if len(w) >= 4}


def _line(*fields) -> str:
    return " | ".join(str(f) for f in fields if f not in (None, ""))


def snapshot(db: Database, cfg: dict, question: str, job_uid: str | None = None,
             sources: set[str] | None = None) -> str:
    """Your data as the AI reads it, in one <dados> block. Never the notes, the name or the signature
    (the CV reader puts the phone and the email there), the keys or any file path."""
    you = {k: v for k, v in profile.from_config(cfg).items() if k not in ("name", "signature")}
    lines = ["# Perfil e procura"]
    lines += [f"{k}: {'; '.join(map(str, v)) if isinstance(v, list) else v}" for k, v in you.items() if v not in ("", [])]
    level = levels.for_ai(cfg.get("search") or {}, i18n.language)
    if level:
        lines.append(level)

    jobs = db.all_jobs()
    lines.append("\n# Estados")
    lines += [f"{s}: {sum(j['status'] == s for j in jobs)}" for s in STATUSES]

    lines.append("\n# Fontes (última procura de cada uma)")
    for run in db.last_runs(sources):
        lines.append(_line(run["source"], f"lidas {run['fetched']}", f"mantidas {run['kept']}", run["status"],
                           run["message"] if run["status"] == "error" else ""))
    for problem in db.source_health(sources):
        lines.append(f"com problemas: {problem['source']} ({problem['kind']})")

    listed = [j for j in jobs if j["status"] != "descartada"]
    lines.append(f"\n# Vagas ativas: {sum(bool(j['active']) for j in listed)}")
    lines.append("uid | título | empresa | local | encaixe | estado | salário | publicada | fonte")
    for j in listed:
        pay = salary.of_job(j)
        lines.append(_line(j["uid"], j["title"], j["company"], j["location"], j["score"], j["status"],
                           pay and pay["text"], j["posted_at"], j["source"],
                           "" if j["active"] else "já não está publicada"))

    cut = db.cut_jobs()
    lines.append("\n# Cortadas na última procura, por motivo")
    reasons: dict[str, int] = {}
    for c in cut:
        reasons[c["reason"]] = reasons.get(c["reason"], 0) + 1
    lines += [f"{reason}: {n}" for reason, n in sorted(reasons.items(), key=lambda r: -r[1])]
    asked = _words(question)
    named = [c for c in cut if asked & _words(c["title"])][:MAX_CUT]
    if named:
        lines.append("Cortadas parecidas com a pergunta:")
        lines += [_line(c["title"], c["company"], c["location"], c["reason"]) for c in named]

    asked_text = normalize(question)
    focus = db.get(job_uid) if job_uid else None
    focus = focus or next((j for j in listed if normalize(j["title"]) and normalize(j["title"]) in asked_text), None)
    if focus:
        lines.append(f"\n# Vaga em foco: {focus['title']} ({focus['company']})")
        lines.append((focus.get("description") or "(sem descrição)")[:MAX_DESCRIPTION])

    # text from job sites can't close the block and pass for instructions
    body = "\n".join(lines).replace("</dados>", "")
    return f"<dados>\n{body}\n</dados>"
