"""The same job on two sites (the company's page and ITJobs, say) is one card, and its status reaches both."""

import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from jobradar.app import create_app
from jobradar.db import Database, duplicate_key
from jobradar.models import Job

ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-11-02T10:00:00+00:00"


def job(source, external_id, title, company="Eurotux", location="Braga", score=50):
    return Job(source=source, external_id=external_id, company=company, title=title, location=location,
               url=f"https://example.com/{source}/{external_id}"), score


def test_same_company_and_title_is_the_same_job():
    key = lambda title, company="Eurotux, S.A.", location="Braga": duplicate_key(
        {"title": title, "company": company, "location": location})
    assert key("Cybersecurity Specialist") == key("Cybersecurity Specialist (M/F) - Braga")
    assert key("Cybersecurity Specialist") == key("CYBERSECURITY SPECIALIST (Ref 004-2026)", company="EUROTUX")
    assert key("Developer (Java)") != key("Developer (Python)")  # other brackets count
    assert key("DevOps Engineer") != key("DevOps Engineer", company="Accenture")  # other company, other job
    assert duplicate_key({"title": "Dev", "company": ""}) is None  # no company: never merged


def test_one_card_with_the_other_sites(tmp_path):
    db = Database(tmp_path / "t.db")
    for j, score in [job("itjobs", "1", "Cybersecurity Specialist", score=70),
                     job("eurotux", "cyber", "Cybersecurity Specialist", score=60),
                     job("itjobs", "2", "DevOps Engineer", company="KCS IT")]:
        db.upsert(j, score, [], {}, NOW)
    jobs = db.all_jobs()
    assert len(jobs) == 2
    cyber = next(j for j in jobs if j["title"] == "Cybersecurity Specialist")
    # the company's own posting is the card, even with a lower score; ITJobs is a link on it
    assert cyber["source"] == "eurotux"
    assert cyber["also_on"] == [{"source": "itjobs", "url": "https://example.com/itjobs/1"}]


def test_same_title_twice_in_one_source_is_two_jobs(tmp_path):
    db = Database(tmp_path / "t.db")
    for j, score in [job("smartrecruiters:BoschGroup", "1", "Data Analyst (f/m/div.)", company="Bosch Group"),
                     job("smartrecruiters:BoschGroup", "2", "Data Analyst (f/m/div.)", company="Bosch Group")]:
        db.upsert(j, score, [], {}, NOW)
    db.update("smartrecruiters:BoschGroup:1", status="candidatei")
    jobs = db.all_jobs()
    assert len(jobs) == 2 and all(j["also_on"] == [] for j in jobs)  # two teams, two postings
    assert db.copies("smartrecruiters:BoschGroup:1") == []  # applying to one doesn't touch the other


def test_status_and_notes_reach_every_copy(tmp_path):
    config_path = tmp_path / "config.yaml"
    shutil.copy(ROOT / "config.example.yaml", config_path)
    client = TestClient(create_app(config_path=config_path, db_path=tmp_path / "t.db"))
    db = client.app.state.db
    for j, score in [job("itjobs", "1", "Cybersecurity Specialist"), job("eurotux", "cyber", "Cybersecurity Specialist")]:
        db.upsert(j, score, [], {}, NOW)

    client.patch("/api/jobs/itjobs:1", json={"status": "candidatei", "notes": "Enviei o CV"})
    copy = db.get("eurotux:cyber")
    assert copy["status"] == "candidatei" and copy["notes"] == "Enviei o CV" and copy["applied_at"]
    # the card is now the one you acted on, and it is still a single card
    [card] = client.get("/api/jobs").json()
    assert card["status"] == "candidatei" and len(card["also_on"]) == 1
