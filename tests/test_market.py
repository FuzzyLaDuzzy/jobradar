"""📊 Market: which skills the relevant, published jobs ask for, and which of them the profile has."""

import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from jobradar import i18n, skills
from jobradar.app import create_app
from jobradar.models import Job

ROOT = Path(__file__).resolve().parents[1]


def job(description, active=True, title="Developer"):
    return {"title": title, "description": description, "active": active, "matches": 1}


def counts(result):
    return {s["name"]: (s["jobs"], s["have"]) for s in result["skills"]}


def test_counts_each_job_once_and_marks_what_you_have():
    jobs = [job("Python and AWS. English required."), job("Python, Azure and AWS"), job("AWS", active=False)]
    result = skills.market(jobs, {"skills": ["python"], "facts": "Native Portuguese speaker"})
    assert result["jobs"] == 2  # the closed job doesn't count
    assert counts(result)["AWS"] == (2, False) and counts(result)["Python"] == (2, True)
    assert counts(result)["Inglês"] == (1, None)  # a language the profile doesn't mention: unknown, not "missing"
    assert {s["name"] for s in result["skills"][:2]} == {"Python", "AWS"}  # most asked first


def test_ambiguous_words_are_not_counted():
    result = counts(skills.market([job("Join the rest of the team. Go to market fast.")], {}))
    assert "REST APIs" not in result and "Go" not in result
    result = counts(skills.market([job("Build RESTful services in Golang")], {"skills": ["rest"]}))
    assert result["REST APIs"] == (1, True)  # "rest" in the profile is the same skill
    assert result["Go"] == (1, False)


def test_languages_known_from_the_profile_and_names_in_english():
    result = skills.market([job("Fluent English")], {"facts": "English (C1)"})
    assert counts(result)["Inglês"] == (1, True)
    i18n.use({"language": "en"})
    assert counts(skills.market([job("Fluent English")], {}))["English"] == (1, None)


def test_market_endpoint(tmp_path):
    config_path = tmp_path / "config.yaml"
    shutil.copy(ROOT / "config.example.yaml", config_path)
    client = TestClient(create_app(config_path=config_path, db_path=tmp_path / "t.db"))
    client.app.state.db.upsert(Job(source="s", external_id="1", company="X", title="Data Engineer", location="Braga",
                                   url="https://x.pt/1", description="Python, Spark and Azure"), 60, [], {}, "2026-11-02")
    data = client.get("/api/market").json()
    assert data["jobs"] == 1
    assert {"name": "Azure", "jobs": 1, "have": False} in data["skills"]
    assert {"name": "Python", "jobs": 1, "have": True} in data["skills"]  # python is in the example profile
