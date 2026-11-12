from __future__ import annotations

import json
import re
import sqlite3
import threading
from datetime import date, datetime, timezone
from pathlib import Path

from .models import Job
from .text import company_key, normalize

STATUSES = ("nova", "guardada", "candidatei", "entrevista", "oferta", "rejeitada", "descartada")
# the statuses of a job you applied to: "Applications" tab, and the date you applied stays
APPLIED = ("candidatei", "entrevista", "oferta", "rejeitada")
_TRACKED = ("guardada",) + APPLIED  # listed even when they no longer pass the filters


# job boards and agencies that repost companies' jobs: the company's own posting is the one kept
AGGREGATORS = {"itjobs", "landingjobs", "netempregos", "randstad", "sysmatch", "workable", "workinbraga", "smartrecruiters_search"}


_GENDER_RE = re.compile(r"\((?:[mfhxd]\s*/\s*)+[a-z]+\.?\)")  # (m/f), (f/m/x), (f/m/div.), (h/m)


def duplicate_key(job: dict) -> str | None:
    """Same company and same title = the same job on two sites (often the company's page and ITJobs).
    The title is compared without "(m/f)", "Ref ...", punctuation, or the job's own place at the end;
    other brackets count, so "Developer (Java)" and "Developer (Python)" stay two jobs."""
    company = company_key(job.get("company"))
    title = _GENDER_RE.sub(" ", re.sub(r"\bref\b.*$", " ", normalize(job.get("title"))))
    words = re.findall(r"[a-z0-9+#]+", title)
    place = set(re.findall(r"[a-z0-9]+", normalize(job.get("location"))))
    while words and words[-1] in place:  # "Cybersecurity Specialist - Braga" in Braga
        words.pop()
    return f"{company}|{' '.join(words)}" if company and words else None


def merge_duplicates(jobs: list[dict]) -> list[dict]:
    """One card per job: the copy you acted on (status or notes), else an active one, else the company's
    own posting, else the best score. The copies from other sites go in `also_on` (source and link).
    Only other sites: two "Data Analyst" postings from the same source are two jobs (two teams)."""
    groups: dict[str, list[dict]] = {}
    for job in jobs:
        key = duplicate_key(job)
        if key:
            groups.setdefault(key, []).append(job)

    def rank(job: dict):
        return (job["status"] != "nova" or bool(job.get("notes")), job["active"],
                job["source"].split(":")[0] not in AGGREGATORS, job.get("score") or 0)

    primary = {key: max(group, key=rank) for key, group in groups.items()}
    merged = []
    for job in jobs:
        key = duplicate_key(job)
        card = primary.get(key)
        if card is not None and card is not job and card["source"] != job["source"]:
            continue  # a copy on another site: a link on the card
        others = groups.get(key, []) if card is job else []
        job["also_on"] = [{"source": j["source"], "url": j["url"]} for j in others if j["source"] != job["source"]]
        merged.append(job)
    return merged


def web_link(url: str | None) -> str:
    """Only http(s) links reach the page: a javascript: link from a feed would run when clicked."""
    url = (url or "").strip()
    return url if url.lower().startswith(("http://", "https://")) else ""

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
-- the jobs the filters cut in the last search of each source, with the reason (the ✂ tab)
CREATE TABLE IF NOT EXISTS cut (
    uid TEXT PRIMARY KEY,
    source TEXT,
    company TEXT,
    title TEXT,
    location TEXT,
    url TEXT,
    posted_at TEXT,
    reason TEXT,
    seen TEXT
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
                url=web_link(job.url),
                posted_at=job.posted_at,
                description=job.description,
                contract=job.contract,
                experience=job.experience,
                work_model=job.work_model,
                logo=web_link(job.logo),
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

    def carry_over(self, source: str, new_uids: set[str]) -> int:
        """A job reposted under a new id: if the old one is gone from the same source, your status, notes and
        application date move to the new one, so a job you applied to doesn't come back as new. Two postings
        that are both still published stay two jobs, as in merge_duplicates."""
        if not new_uids:
            return 0
        with self._lock:
            old = [dict(r) for r in self.conn.execute(
                "SELECT uid, company, title, location, status, notes, applied_at FROM jobs "
                "WHERE source = ? AND active = 0 AND (status != 'nova' OR notes != '') ORDER BY last_seen DESC",
                (source,))]
            moved = 0
            for uid in new_uids:
                new = self.conn.execute("SELECT company, title, location, flags FROM jobs WHERE uid = ?", (uid,)).fetchone()
                key = duplicate_key(dict(new)) if new else None
                match = next((o for o in old if key and duplicate_key(o) == key), None)
                if match is None:
                    continue
                old.remove(match)
                flags = json.loads(new["flags"] or "{}") | {"reposted": True}
                self.conn.execute("UPDATE jobs SET status = ?, notes = ?, applied_at = ?, flags = ? WHERE uid = ?",
                                  (match["status"], match["notes"], match["applied_at"], json.dumps(flags), uid))
                # the old copy is closed and out of the list: everything you had on it is on the new one now
                self.conn.execute("UPDATE jobs SET status = 'nova', notes = '', applied_at = NULL, matches = 0 "
                                  "WHERE uid = ?", (match["uid"],))
                moved += 1
            self.conn.commit()
        return moved

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
        return merge_duplicates([_row_to_dict(r) for r in rows])

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
            if status in APPLIED:  # the first click is the date you applied; interview, offer... keep it
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

    def _listed(self) -> list[dict]:
        """Jobs that pass the current filters, plus any you saved or applied to."""
        rows = self.conn.execute(
            f"SELECT * FROM jobs WHERE matches = 1 OR status IN ({', '.join(repr(s) for s in _TRACKED)}) "
            "ORDER BY score DESC, posted_at DESC"
        ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def all_jobs(self) -> list[dict]:
        return merge_duplicates(self._listed())

    def copies(self, uid: str) -> list[str]:
        """The other copies of a job on other sites (see duplicate_key), so a status or note reaches all."""
        job = self.get(uid)
        key = duplicate_key(job) if job else None
        return [j["uid"] for j in self._listed()
                if key and j["source"] != job["source"] and duplicate_key(j) == key]

    def decision_examples(self, limit: int = 8) -> dict:
        """Your latest choices, for the AI score: jobs you applied to or saved, and jobs you discarded."""
        def titles(statuses: tuple[str, ...]) -> list[str]:
            marks = ", ".join("?" for _ in statuses)
            rows = self.conn.execute(
                f"SELECT title, company FROM jobs WHERE status IN ({marks}) "
                "ORDER BY COALESCE(applied_at, last_seen) DESC LIMIT ?", (*statuses, limit)).fetchall()
            return [f"{r['title']} ({r['company']})" if r["company"] else r["title"] for r in rows]

        return {"liked": titles(_TRACKED), "disliked": titles(("descartada",))}

    def acted_on(self) -> list[dict]:
        """The jobs you did something with: applied, saved, discarded, or wrote notes about (the CSV export)."""
        rows = self.conn.execute(
            "SELECT * FROM jobs WHERE status != 'nova' OR notes != '' "
            "ORDER BY applied_at IS NULL, applied_at DESC, status, score DESC"
        ).fetchall()
        return [_row_to_dict(r) for r in rows]

    # --- cut by the filters -------------------------------------------------
    def replace_cut(self, source: str, cut: list[tuple[Job, str]], now: str) -> None:
        """What one source's search cut, and why: replaces that source's earlier list."""
        with self._lock:
            self.conn.execute("DELETE FROM cut WHERE source = ?", (source,))
            self.conn.executemany(
                "INSERT OR REPLACE INTO cut (uid, source, company, title, location, url, posted_at, reason, seen) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(job.uid, source, job.company, job.title, job.location, web_link(job.url), job.posted_at, reason, now)
                 for job, reason in cut])
            self.conn.commit()

    def cut_jobs(self) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM cut ORDER BY reason LIKE 'fora da área%', title").fetchall()
        return [dict(r) for r in rows]

    # --- runs -------------------------------------------------------------
    def add_run(self, **run) -> None:
        with self._lock:
            cols = ", ".join(run)
            marks = ", ".join("?" for _ in run)
            self.conn.execute(f"INSERT INTO runs ({cols}) VALUES ({marks})", tuple(run.values()))
            self.conn.commit()

    def source_health(self, sources: set[str] | None = None, window: int = 3) -> list[dict]:
        """Sources that look broken, from their last `window` searches: an error every time, nothing read after
        having read jobs before, or nothing read ever. A site that changes its pages fails like this, quietly.
        `sources`: the ones still in the config (the others' old runs don't count)."""
        runs: dict[str, list[sqlite3.Row]] = {}
        for row in self.conn.execute("SELECT source, status, fetched, message FROM runs ORDER BY id DESC"):
            runs.setdefault(row["source"], []).append(row)
        problems = []
        for source, history in sorted(runs.items()):
            last = history[:window]
            if (sources is not None and source not in sources) or len(last) < window:
                continue
            before = max((r["fetched"] or 0 for r in history[window:]), default=0)
            if all(r["status"] == "error" for r in last):
                problems.append({"source": source, "kind": "error", "runs": window, "message": last[0]["message"] or ""})
            elif all(r["status"] == "ok" and not r["fetched"] for r in last):
                problems.append({"source": source, "kind": "empty" if before else "never",
                                 "runs": window if before else len(history), "before": before})
        return problems

    def last_runs(self, sources: set[str] | None = None) -> list[dict]:
        """The last search of each source. `sources`: the ones still in the config (a source taken out stops showing)."""
        rows = self.conn.execute(
            "SELECT * FROM runs WHERE id IN (SELECT MAX(id) FROM runs GROUP BY source) "
            "ORDER BY source"
        ).fetchall()
        return [dict(r) for r in rows if sources is None or r["source"] in sources]


def _row_to_dict(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["reasons"] = json.loads(data.get("reasons") or "[]")
    data["flags"] = json.loads(data.get("flags") or "{}")
    data["active"] = bool(data.get("active"))
    return data
