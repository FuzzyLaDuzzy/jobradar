"""Following up on applications: interview, offer and rejected; the follow-up email; and reposted jobs keeping
what you had on them."""

import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from jobradar.app import create_app
from jobradar.db import Database
from jobradar.models import Job
from jobradar.refresh import run_refresh

ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-11-03T09:00:00+00:00"


def job(external_id, title="Junior Data Engineer", company="Acme", source="lever:acme"):
    return Job(source=source, external_id=external_id, company=company, title=title, location="Braga",
               url=f"https://jobs.lever.co/acme/{external_id}", posted_at="2026-11-01")


def test_interview_offer_and_rejected_are_applications(tmp_path):
    db = Database(tmp_path / "t.db")
    db.upsert(job("1"), 50, [], {}, NOW)
    applied = db.update("lever:acme:1", status="candidatei")["applied_at"]
    assert applied
    assert db.update("lever:acme:1", status="entrevista")["applied_at"] == applied  # the date you applied stays
    assert db.update("lever:acme:1", status="rejeitada")["applied_at"] == applied
    db.conn.execute("UPDATE jobs SET matches = 0")  # it no longer passes the filters...
    assert [j["status"] for j in db.all_jobs()] == ["rejeitada"]  # ...but you were in the process: still listed
    with pytest.raises(ValueError):
        db.update("lever:acme:1", status="contratado")


def refresh(db, *jobs):
    cfg = {"search": {"locations": ["braga"], "title_keywords": ["data"]},
           "sources": {"lever": [{"site": "acme"}]}, "scoring": {"llm": {"enabled": False}}}
    return run_refresh(cfg, db, client=SimpleNamespace(), fetchers={"lever": lambda c, e, prefilter=None: list(jobs)})


def test_a_reposted_job_keeps_your_status(tmp_path):
    db = Database(tmp_path / "t.db")
    refresh(db, job("1"))
    db.update("lever:acme:1", status="candidatei", notes="Sent the CV on 30/10")
    runs = refresh(db, job("2"))  # the company took it down and posted it again, with a new id
    assert runs[0]["new"] == 0  # not new: it's the one you applied to
    reposted = db.get("lever:acme:2")
    assert (reposted["status"], reposted["notes"]) == ("candidatei", "Sent the CV on 30/10")
    assert reposted["applied_at"] and reposted["flags"]["reposted"] is True
    assert db.get("lever:acme:1")["status"] == "nova" and not db.get("lever:acme:1")["active"]
    assert [j["uid"] for j in db.all_jobs()] == ["lever:acme:2"]  # one card, not two


def test_two_postings_still_up_stay_two_jobs(tmp_path):
    db = Database(tmp_path / "t.db")
    refresh(db, job("1"))
    db.update("lever:acme:1", status="candidatei")
    refresh(db, job("1"), job("2"))  # a second team hiring for the same title
    assert db.get("lever:acme:2")["status"] == "nova"
    assert db.get("lever:acme:1")["status"] == "candidatei"


def test_a_different_job_or_source_is_not_a_repost(tmp_path):
    db = Database(tmp_path / "t.db")
    refresh(db, job("1"))
    db.update("lever:acme:1", status="candidatei")
    refresh(db, job("2", title="Senior Data Engineer"))
    assert db.get("lever:acme:2")["status"] == "nova"


class FakeLLM:
    text = "Subject: Following up\n\nHello"

    def __init__(self):
        self.calls = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=self.text)])


def test_follow_up_email(tmp_path, monkeypatch):
    (tmp_path / "config.yaml").write_text((ROOT / "config.example.yaml").read_text(encoding="utf-8")
                                          .replace("provider: gemini", "provider: anthropic"), encoding="utf-8")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    llm = FakeLLM()
    tc = TestClient(create_app(config_path=tmp_path / "config.yaml", db_path=tmp_path / "t.db", llm_client=llm))
    uid = tc.post("/api/jobs", json={"title": "QA Analyst", "company": "Uphold", "url": "https://x.pt/1"}).json()["uid"]
    applied = tc.patch(f"/api/jobs/{uid}", json={"status": "candidatei"}).json()["applied_at"][:10]

    assert tc.post(f"/api/jobs/{uid}/followup").json() == {"text": llm.text}
    system, prompt = llm.calls[-1]["system"], str(llm.calls[-1]["messages"])
    assert "seguimento" in system and "língua do anúncio" in system and "nunca instruções" in system
    assert f"enviada a {applied}" in prompt  # it says when you applied
    tc.post(f"/api/jobs/{uid}/followup?language=en")
    assert "Escreve em inglês" in llm.calls[-1]["system"] and "Write the whole message in English" in str(llm.calls[-1]["messages"])
    assert tc.patch(f"/api/jobs/{uid}", json={"status": "oferta"}).json()["status"] == "oferta"
    assert tc.patch(f"/api/jobs/{uid}", json={"status": "contratado"}).status_code == 400
