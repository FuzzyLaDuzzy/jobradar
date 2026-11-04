"""Fetch every configured source, filter, score and store the results."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Callable

import httpx

from . import scoring
from .db import Database
from .filters import evaluate, quick_reject
from .models import Job
from .sources import FETCHERS, SourceSkipped, make_client, source_label, with_area

log = logging.getLogger("jobradar")
FETCH_THREADS = 8  # platforms read at the same time


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _fetch_all(cfg: dict, client, fetchers: dict[str, Callable], prefilter) -> list[tuple]:
    """(kind, entry, started, finished, jobs or the exception) for every source, in the config's order.
    The platforms are read at the same time, but the sources of one platform still one after the other:
    no site gets more requests at once than before (Lever's 1 a second, say)."""
    search = cfg.get("search") or {}
    groups = [(kind, fetchers[kind], entries or []) for kind, entries in (cfg.get("sources") or {}).items()
              if kind in fetchers]

    def read(group):
        kind, fetch, entries = group
        results = []
        for entry in entries:
            started = _now()
            try:
                jobs = fetch(client, with_area(kind, entry, search, cfg.get("sources")), prefilter=prefilter)
            except Exception as exc:  # judged with the others, below
                jobs = exc
            results.append((kind, entry, started, _now(), jobs))
        return results

    with ThreadPoolExecutor(max_workers=FETCH_THREADS) as pool:
        return [result for group in pool.map(read, groups) for result in group]


def run_refresh(
    cfg: dict,
    db: Database,
    client: httpx.Client | None = None,
    fetchers: dict[str, Callable] | None = None,
    llm_client=None,
    score: bool = True,
) -> list[dict]:
    """score=False: leave the AI scoring to the caller (the app does it after answering: score_new)."""
    fetchers = fetchers or FETCHERS
    search = cfg.get("search") or {}
    own_client = client is None
    client = client or make_client()
    summaries: list[dict] = []

    def prefilter(job: Job) -> bool:
        return quick_reject(job, search) is None

    try:
        for kind, entry, started, finished, jobs in _fetch_all(cfg, client, fetchers, prefilter):
            label = source_label(kind, entry)
            summary = dict(source=label, started_at=started, fetched=0, kept=0, new=0)
            if isinstance(jobs, SourceSkipped):
                summary.update(status="skipped", message=str(jobs))
            elif isinstance(jobs, (RuntimeError, httpx.HTTPError)):  # API said no, network down
                log.warning("Fonte %s falhou: %s", label, jobs)
                summary.update(status="error", message=str(jobs))
            elif isinstance(jobs, Exception):  # unexpected: API format changed, bug...
                log.error("Fonte %s falhou", label, exc_info=jobs)
                summary.update(status="error", message=f"{type(jobs).__name__}: {jobs}")
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
            summary["finished_at"] = finished
            db.add_run(**summary)
            summaries.append(summary)
    finally:
        if own_client:
            client.close()

    if score and (scoring.llm_available(cfg) or llm_client is not None):
        score_new(cfg, db, llm_client)
    return summaries


def score_new(cfg: dict, db: Database, llm_client=None) -> None:
    """The AI's score for the jobs that don't have one yet (up to max_jobs_per_refresh)."""
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
