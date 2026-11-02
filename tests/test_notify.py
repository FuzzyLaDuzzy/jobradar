import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

from jobradar import notify
from jobradar.db import Database
from jobradar.models import Job


class FakeKey:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def capture(monkeypatch, registry=None):
    """Record the PowerShell calls; the registry is faked so tests never write to the real one."""
    calls, registry = [], {} if registry is None else registry
    monkeypatch.setattr(notify.sys, "platform", "win32")
    monkeypatch.setattr(notify.subprocess, "run", lambda args, **kw: calls.append((args, kw["env"]["JOBRADAR_TOAST"])))
    monkeypatch.setattr(notify, "winreg", SimpleNamespace(
        HKEY_CURRENT_USER="HKCU", REG_SZ=1,
        CreateKey=lambda root, path: registry.update(path=path) or FakeKey(),
        SetValueEx=lambda key, name, reserved, kind, value: registry.update({name: value}),
    ))
    return calls


def test_toast_shows_jobradar_with_its_icon(monkeypatch):
    registry = {}
    calls = capture(monkeypatch, registry)
    notify.show([{"title": "Dev", "company": "X"}], "http://127.0.0.1:8000")
    assert registry["path"] == r"Software\Classes\AppUserModelId\JobRadar"  # per-user, no admin
    assert registry["DisplayName"] == "JobRadar" and Path(registry["IconUri"]).is_file()
    assert "'JobRadar'" in calls[0][0][-1]  # the toast is sent with that id


def test_notification_lists_the_best_new_jobs(monkeypatch):
    calls = capture(monkeypatch)
    jobs = [{"title": "AWS Cloud Engineer", "company": "Continental"}, {"title": "Java Dev", "company": ""},
            {"title": "QA Analyst", "company": "Uphold"}]
    notify.show(jobs, "http://127.0.0.1:8000")
    texts = [t.text for t in ET.fromstring(calls[0][1]).iter("text")]
    assert texts == ["JobRadar: 3 vagas novas", "AWS Cloud Engineer · Continental", "Java Dev (e mais 1)"]


def test_job_titles_never_reach_the_command_line(monkeypatch):
    # titles come from job sites: they travel as data in an env var, never inside the PowerShell code
    calls = capture(monkeypatch)
    evil = 'Dev "$(Remove-Item C:\\x)" <b>&'
    notify.show([{"title": evil, "company": "X"}], "http://127.0.0.1:8000")
    args, toast = calls[0]
    assert "Remove-Item" not in " ".join(args)
    assert ET.fromstring(toast).find(".//text[2]").text == evil + " · X"  # escaped, still valid XML


def test_no_notification_without_new_jobs(monkeypatch):
    calls = capture(monkeypatch)
    notify.show([], "http://127.0.0.1:8000")
    assert calls == []


def test_backup_keeps_the_last_7_days(tmp_path):
    import sqlite3

    db = Database(tmp_path / "jobradar.db")
    db.upsert(Job(source="s", external_id="1", company="A", title="Dev", location="Braga", url="u"),
              10, [], {}, "2026-11-01T09:00:00+00:00")
    folder = tmp_path / "backups"
    folder.mkdir()
    for day in range(1, 10):  # older copies
        (folder / f"jobradar-2026-10-{day:02d}.db").write_bytes(b"old")
    copy = db.backup(folder)
    con = sqlite3.connect(copy)
    assert con.execute("SELECT title FROM jobs").fetchone()[0] == "Dev"
    con.close()
    names = sorted(p.name for p in folder.glob("jobradar-*.db"))
    assert len(names) == 7 and copy.name in names and "jobradar-2026-10-01.db" not in names


def test_new_since_only_returns_jobs_from_this_refresh(tmp_path):
    db = Database(tmp_path / "t.db")
    old = Job(source="s", external_id="1", company="A", title="Old", location="Braga", url="u")
    new = Job(source="s", external_id="2", company="B", title="New", location="Braga", url="u")
    db.upsert(old, 10, [], {}, "2026-11-01T09:00:00+00:00")
    db.upsert(new, 50, [], {}, "2026-11-01T21:00:05+00:00")
    assert [j["title"] for j in db.new_since("2026-11-01T21:00:00+00:00")] == ["New"]
