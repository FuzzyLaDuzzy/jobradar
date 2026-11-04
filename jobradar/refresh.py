"""Fetch every configured source, filter, score and store the results."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable

import httpx

from . import scoring
from .db import Database
from .filters import evaluate, quick_reject
from .models import Job
from .sources import FETCHERS, SourceSkipped, make_client, source_label, with_area

log = logging.getLogger("jobradar")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_refresh(
    cfg: dict,
    db: Database,
    client: httpx.Client | None = None,
    fetchers: dict[str, Callable] | None = None,
    llm_client=None,
) -> list[dict]:
    fetchers = fetchers or FETCHERS
    search = cfg.get("search") or {}
    own_client = client is None
    client = client or make_client()
    summaries: list[dict] = []

    def prefilter(job: Job) -> bool:
        return quick_reject(job, search) is None

    try:
        for kind, entries in (cfg.get("sources") or {}).items():
            fetch = fetchers.get(kind)
            if fetch is None:
                continue
            for entry in entries or []:
                label = source_label(kind, entry)
                started = _now()
                summary = dict(source=label, started_at=started, fetched=0, kept=0, new=0)
                try:
                    jobs = fetch(client, with_area(kind, entry, search, cfg.get("sources")), prefilter=prefilter)
                except SourceSkipped as exc:
                    summary.update(status="skipped", message=str(exc))
                except (RuntimeError, httpx.HTTPError) as exc:  # API said no, network down
                    log.warning("Fonte %s falhou: %s", label, exc)
                    summary.update(status="error", message=str(exc))
                except Exception as exc:  # unexpected: API format changed, bug...
                    log.exception("Fonte %s falhou", label)
                    summary.update(status="error", message=f"{type(exc).__name__}: {exc}")
                else:
                    now = _now()
                    for job in jobs:  # sources without logos use the one in config.yaml
                        job.logo = job.logo or entry.get("logo", "")
                    summary["fetched"] = len(jobs)
                    kept: set[str] = set()
                    new: set[str] = set()
                    cut: list[tuple[Job, str]] = []  # shown in the ✂ tab, to catch good jobs cut by mistake
                    for job in jobs:
                        keep, reason, flags = evaluate(job, search)
                        if not keep:
                            cut.append((job, reason or ""))
                            continue
                        kw, reasons = scoring.keyword_score(job, cfg, flags)
                        kept.add(job.uid)
                        if db.upsert(job, kw, reasons, flags, now):
                            new.add(job.uid)
                    summary["kept"] = len(kept)
                    fetched = {j.uid for j in jobs}
                    db.mark_gone(label, fetched)
                    # a repost of a job you acted on isn't new: it keeps your status (after mark_gone: the old one is gone)
                    summary["new"] = len(new) - db.carry_over(label, new)
                    db.mark_unmatched(label, fetched, kept)
                    db.replace_cut(label, cut, now)
                    summary.update(status="ok", message="")
                summary["finished_at"] = _now()
                db.add_run(**summary)
                summaries.append(summary)
    finally:
        if own_client:
            client.close()

    if scoring.llm_available(cfg) or llm_client is not None:
        _score_with_llm(cfg, db, llm_client)
    return summaries


def _score_with_llm(cfg: dict, db: Database, llm_client=None) -> None:
    limit = int(((cfg.get("scoring") or {}).get("llm") or {}).get("max_jobs_per_refresh", 40))
    examples = db.decision_examples()  # your choices so far: jobs like the ones you applied to score higher
    for row in db.unscored(limit):
        job = Job(
            source=row["source"],
            external_id=row["external_id"],
            company=row["company"],
            title=row["title"],
            location=row["location"],
            url=row["url"],
            description=row["description"] or "",
            contract=row["contract"] or "",
            experience=row["experience"] or "",
            work_model=row["work_model"] or "",
        )
        try:
            result = scoring.llm_score(job, cfg, llm_client, examples)
        except Exception:  # never let the LLM break a refresh
            log.exception("LLM scoring failed for %s", row["uid"])
            break
        if result:
            db.set_llm(row["uid"], *result)
