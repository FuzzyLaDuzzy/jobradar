from __future__ import annotations

import json
import sqlite3
import threading
from datetime import date, datetime, timezone
from pathlib import Path

from .models import Job

STATUSES = ("nova", "guardada", "candidatei", "descartada")

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    uid TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    company TEXT,
    title TEXT,
    location TEXT,
    url TEXT,
    posted_at TEXT,
    description TEXT,
    contract TEXT,
    experience TEXT,
    work_model TEXT,
    logo TEXT,
    kw_score INTEGER DEFAULT 0,
    llm_score INTEGER,
    llm_reason TEXT,
    score INTEGER DEFAULT 0,
    reasons TEXT DEFAULT '[]',
    flags TEXT DEFAULT '{}',
    status TEXT DEFAULT 'nova',
    notes TEXT DEFAULT '',
    first_seen TEXT,
    last_seen TEXT,
    active INTEGER DEFAULT 1,
    matches INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT,
    started_at TEXT,
    finished_at TEXT,
    fetched INTEGER DEFAULT 0,
    kept INTEGER DEFAULT 0,
    new INTEGER DEFAULT 0,
    status TEXT,
    message TEXT
);
"""


class Database:
    def __init__(self, path: Path | str = "jobradar.db"):
        self.path = str(path)
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        columns = {r["name"] for r in self.conn.execute("PRAGMA table_info(jobs)")}
        for name, kind in (("matches", "INTEGER DEFAULT 1"), ("logo", "TEXT"), ("applied_at", "TEXT")):
            if name not in columns:  # databases created by older versions
                self.conn.execute(f"ALTER TABLE jobs ADD COLUMN {name} {kind}")
        self.conn.commit()

    # --- jobs -------------------------------------------------------------
    def upsert(self, job: Job, kw_score: int, reasons: list[str], flags: dict, now: str) -> bool:
        """Insert or refresh a job. Keeps status/notes/LLM score. Returns True if new."""
        with self._lock:
            row = self.conn.execute(
                "SELECT llm_score FROM jobs WHERE uid = ?", (job.uid,)
            ).fetchone()
            fields = dict(
                source=job.source,
                external_id=job.external_id,
                company=job.company,
                title=job.title,
                location=job.location,
                url=job.url,
                posted_at=job.posted_at,
                description=job.description,
                contract=job.contract,
                experience=job.experience,
                work_model=job.work_model,
                logo=job.logo,
                kw_score=kw_score,
                reasons=json.dumps(reasons, ensure_ascii=False),
                flags=json.dumps(flags),
                last_seen=now,
                active=1,
                matches=1,
            )
            if row is None:
                fields.update(uid=job.uid, first_seen=now, score=kw_score, status="nova")
                cols = ", ".join(fields)
                marks = ", ".join("?" for _ in fields)
                self.conn.execute(
                    f"INSERT INTO jobs ({cols}) VALUES ({marks})", tuple(fields.values())
                )
            else:
                from .scoring import combine

                fields["score"] = combine(kw_score, row["llm_score"])
                sets = ", ".join(f"{k} = ?" for k in fields)
                self.conn.execute(
                    f"UPDATE jobs SET {sets} WHERE uid = ?", (*fields.values(), job.uid)
                )
            self.conn.commit()
            return row is None

    def mark_gone(self, source: str, seen_uids: set[str]) -> int:
        """Jobs from `source` that no longer appear are marked inactive (closed)."""
        with self._lock:
            rows = self.conn.execute(
                "SELECT uid FROM jobs WHERE source = ? AND active = 1", (source,)
            ).fetchall()
            gone = [r["uid"] for r in rows if r["uid"] not in seen_uids]
            self.conn.executemany("UPDATE jobs SET active = 0 WHERE uid = ?", [(u,) for u in gone])
            self.conn.commit()
            return len(gone)

    def mark_unmatched(self, source: str, fetched: set[str], kept: set[str]) -> int:
        """Jobs still published but that no longer pass the filters (e.g. after
        changing the locations) are hidden instead of lingering in the list."""
        dropped = [(uid,) for uid in fetched - kept]
        with self._lock:
            self.conn.executemany(
                "UPDATE jobs SET matches = 0 WHERE uid = ? AND source = ?",
                [(uid, source) for (uid,) in dropped],
            )
            self.conn.commit()
        return len(dropped)

    def set_llm(self, uid: str, llm_score: int, reason: str) -> None:
        from .scoring import combine

        with self._lock:
            row = self.conn.execute("SELECT kw_score FROM jobs WHERE uid = ?", (uid,)).fetchone()
            if row is None:
                return
            self.conn.execute(
                "UPDATE jobs SET llm_score = ?, llm_reason = ?, score = ? WHERE uid = ?",
                (llm_score, reason, combine(row["kw_score"], llm_score), uid),
            )
            self.conn.commit()

    def new_since(self, since: str) -> list[dict]:
        """Jobs first seen at or after `since` (a refresh's start) that pass the filters, best first."""
        rows = self.conn.execute(
            "SELECT * FROM jobs WHERE first_seen >= ? AND matches = 1 AND active = 1 ORDER BY score DESC",
            (since,),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def unscored(self, limit: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM jobs WHERE llm_score IS NULL AND active = 1 AND status != 'descartada' "
            "ORDER BY kw_score DESC LIMIT ?",
            (limit,),
        ).fetchall()

    def update(self, uid: str, status: str | None = None, notes: str | None = None) -> dict | None:
        if status is not None and status not in STATUSES:
            raise ValueError(f"Estado inválido: {status}")
        with self._lock:
            if status is not None:
                self.conn.execute("UPDATE jobs SET status = ? WHERE uid = ?", (status, uid))
            if status == "candidatei":  # the first click is the date you applied
                now = datetime.now(timezone.utc).isoformat(timespec="seconds")
                self.conn.execute("UPDATE jobs SET applied_at = COALESCE(applied_at, ?) WHERE uid = ?", (now, uid))
            elif status in ("nova", "guardada"):  # un-applied; a later rejection (descartada) keeps the date
                self.conn.execute("UPDATE jobs SET applied_at = NULL WHERE uid = ?", (uid,))
            if notes is not None:
                self.conn.execute("UPDATE jobs SET notes = ? WHERE uid = ?", (notes, uid))
            self.conn.commit()
        return self.get(uid)

    def backup(self, folder: Path | str, keep: int = 7) -> Path:
        """Today's copy of the database (your states and notes exist nowhere else), keeping the last `keep` days.

        SQLite's backup API copies a consistent snapshot even while the app is writing."""
        folder = Path(folder)
        folder.mkdir(exist_ok=True)
        target = folder / f"jobradar-{date.today().isoformat()}.db"
        copy = sqlite3.connect(target)
        try:
            with self._lock:
                self.conn.backup(copy)
        finally:
            copy.close()
        for old in sorted(folder.glob("jobradar-*.db"))[:-keep]:
            old.unlink()
        return target

    def get(self, uid: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM jobs WHERE uid = ?", (uid,)).fetchone()
        return _row_to_dict(row) if row else None

    def all_jobs(self) -> list[dict]:
        """Jobs that pass the current filters, plus any you saved or applied to."""
        rows = self.conn.execute(
            "SELECT * FROM jobs WHERE matches = 1 OR status IN ('guardada', 'candidatei') "
            "ORDER BY score DESC, posted_at DESC"
        ).fetchall()
        return [_row_to_dict(r) for r in rows]

    # --- runs -------------------------------------------------------------
    def add_run(self, **run) -> None:
        with self._lock:
            cols = ", ".join(run)
            marks = ", ".join("?" for _ in run)
            self.conn.execute(f"INSERT INTO runs ({cols}) VALUES ({marks})", tuple(run.values()))
            self.conn.commit()

    def last_runs(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM runs WHERE id IN (SELECT MAX(id) FROM runs GROUP BY source) "
            "ORDER BY source"
        ).fetchall()
        return [dict(r) for r in rows]


def _row_to_dict(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["reasons"] = json.loads(data.get("reasons") or "[]")
    data["flags"] = json.loads(data.get("flags") or "{}")
    data["active"] = bool(data.get("active"))
    return data
