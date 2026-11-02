import re
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from jobradar.app import create_app
from jobradar.models import Job
from jobradar.sources import SourceSkipped

ROOT = Path(__file__).resolve().parents[1]

JOBS = [
    Job(source="smartrecruiters:BoschGroup", external_id="1", company="Bosch",
        title="Junior AI Software Engineer", location="Braga, Portugal",
        url="https://jobs.smartrecruiters.com/BoschGroup/1", posted_at="2026-10-28",
        description="Python, LLM, REST APIs, Kubernetes"),
    Job(source="smartrecruiters:BoschGroup", external_id="2", company="Bosch",
        title="Senior Embedded Engineer", location="Braga, Portugal",
        url="https://jobs.smartrecruiters.com/BoschGroup/2", posted_at="2026-10-28"),
]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    config_path = tmp_path / "config.yaml"
    shutil.copy(ROOT / "config.example.yaml", config_path)
    state = {"jobs": list(JOBS)}

    def fake_sr(client, entry, prefilter=None):
        return list(state["jobs"])

    def fake_skip(client, entry, prefilter=None):
        raise SourceSkipped("Falta ITJOBS_API_KEY")

    def fake_error(client, entry, prefilter=None):
        raise ConnectionError("network down")

    fetchers = {"smartrecruiters": fake_sr, "itjobs": fake_skip, "lever": fake_error,
                "workday": lambda c, e, prefilter=None: []}
    app = create_app(config_path=config_path, db_path=tmp_path / "test.db",
                     refresh_kwargs={"fetchers": fetchers, "client": SimpleNamespace()})
    tc = TestClient(app)
    tc.state = state
    return tc


def test_refresh_filters_stores_and_reports(client):
    runs = {r["source"]: r for r in client.post("/api/refresh").json()["runs"]}
    assert runs["smartrecruiters:BoschGroup"] == {**runs["smartrecruiters:BoschGroup"],
                                                  "status": "ok", "fetched": 2, "kept": 1, "new": 1}
    assert runs["itjobs"]["status"] == "skipped"
    assert runs["lever:farfetch"]["status"] == "error"
    assert "network down" in runs["lever:farfetch"]["message"]

    jobs = client.get("/api/jobs").json()
    assert [j["title"] for j in jobs] == ["Junior AI Software Engineer"]
    assert jobs[0]["status"] == "nova" and jobs[0]["score"] > 0

    # second refresh: nothing new
    runs = {r["source"]: r for r in client.post("/api/refresh").json()["runs"]}
    assert runs["smartrecruiters:BoschGroup"]["new"] == 0
    assert len(client.get("/api/runs").json()) == len(runs)  # last run per source, not both refreshes


def test_add_job_by_hand(client):
    # a job found where JobRadar can't look (e.g. LinkedIn), tracked with the others
    body = {"title": "Junior Developer", "company": "Startup X", "url": "https://www.linkedin.com/jobs/view/123",
            "location": "Braga", "notes": "Vista no LinkedIn"}
    job = client.post("/api/jobs", json=body).json()
    assert (job["source"], job["status"], job["notes"]) == ("manual", "guardada", "Vista no LinkedIn")
    client.patch(f"/api/jobs/{job['uid']}", json={"status": "candidatei"})

    # the same link again: no duplicate, and the status you set is kept
    again = client.post("/api/jobs", json={**body, "notes": ""}).json()
    assert again["uid"] == job["uid"] and again["status"] == "candidatei"

    client.post("/api/refresh")  # the sources never touch it
    manual = [j for j in client.get("/api/jobs").json() if j["source"] == "manual"]
    assert [(j["title"], j["status"], j["notes"]) for j in manual] == [
        ("Junior Developer", "candidatei", "Vista no LinkedIn")]


def test_applied_date(client):
    from datetime import datetime, timezone

    uid = client.post("/api/jobs", json={"title": "Dev", "url": "https://x.pt/9"}).json()["uid"]
    set_status = lambda status: client.patch(f"/api/jobs/{uid}", json={"status": status}).json()["applied_at"]
    applied = set_status("candidatei")
    assert applied[:10] == datetime.now(timezone.utc).date().isoformat()
    assert set_status("candidatei") == applied  # the first click is the date
    assert set_status("descartada") == applied  # a rejection later keeps it
    assert set_status("nova") is None  # un-applying clears it


def test_add_job_rejects_bad_input(client):
    assert client.post("/api/jobs", json={"title": "   "}).status_code == 422
    # the link ends up in an href: a javascript: link would run when clicked
    assert client.post("/api/jobs", json={"title": "Dev", "url": "javascript:alert(1)"}).status_code == 422


def test_installable_as_phone_app(client):
    # Android installs it from the browser (through `tailscale serve`, which adds HTTPS)
    assert 'rel="manifest" href="/static/manifest.json"' in client.get("/").text
    manifest = client.get("/static/manifest.json").json()
    assert (manifest["display"], manifest["start_url"]) == ("standalone", "/")
    assert {"192x192", "512x512"} <= {i["sizes"] for i in manifest["icons"]}
    for icon in manifest["icons"]:
        assert client.get(icon["src"]).status_code == 200


def test_logo_from_config_when_the_source_has_none(tmp_path):
    from jobradar.db import Database
    from jobradar.refresh import run_refresh

    cfg = {"search": {"locations": ["braga"]},
           "sources": {"lever": [{"site": "x", "logo": "https://example.com/x.png"}]}}
    jobs = [Job(source="lever:x", external_id="1", company="X", title="Junior Dev", location="Braga", url="u"),
            Job(source="lever:x", external_id="2", company="Y", title="Trainee", location="Braga", url="u",
                logo="https://example.com/own.png")]
    db = Database(tmp_path / "t.db")
    run_refresh(cfg, db, client=SimpleNamespace(), fetchers={"lever": lambda c, e, prefilter=None: jobs})
    assert {j["external_id"]: j["logo"] for j in db.all_jobs()} == {
        "1": "https://example.com/x.png", "2": "https://example.com/own.png"}


def test_old_database_gets_the_logo_column(tmp_path):
    import sqlite3

    from jobradar.db import Database

    path = tmp_path / "old.db"
    sqlite3.connect(path).execute("CREATE TABLE jobs (uid TEXT PRIMARY KEY, source TEXT NOT NULL, "
                                  "external_id TEXT NOT NULL, status TEXT DEFAULT 'nova')").connection.commit()
    db = Database(path)
    assert {"logo", "matches"} <= {r["name"] for r in db.conn.execute("PRAGMA table_info(jobs)")}


def test_status_and_notes_survive_refresh(client):
    client.post("/api/refresh")
    uid = "smartrecruiters:BoschGroup:1"
    r = client.patch(f"/api/jobs/{uid}", json={"status": "candidatei", "notes": "Enviei email"})
    assert r.status_code == 200 and r.json()["status"] == "candidatei"
    assert client.patch(f"/api/jobs/{uid}", json={"status": "xpto"}).status_code == 400
    assert client.patch("/api/jobs/nope", json={"status": "nova"}).status_code == 404

    client.post("/api/refresh")
    job = client.get("/api/jobs").json()[0]
    assert job["status"] == "candidatei" and job["notes"] == "Enviei email"


def test_closed_jobs_become_inactive(client):
    client.post("/api/refresh")
    client.state["jobs"] = []
    client.post("/api/refresh")
    job = client.get("/api/jobs").json()[0]
    assert job["active"] is False


def test_changing_locations_hides_old_jobs_but_keeps_tracked_ones(client):
    client.state["jobs"] = JOBS + [
        Job(source="smartrecruiters:BoschGroup", external_id="3", company="Bosch",
            title="Junior Data Engineer", location="Braga, Portugal",
            url="https://jobs.smartrecruiters.com/BoschGroup/3", posted_at="2026-10-28"),
    ]
    client.post("/api/refresh")
    assert len(client.get("/api/jobs").json()) == 2
    client.patch("/api/jobs/smartrecruiters:BoschGroup:3", json={"status": "candidatei"})

    # The jobs are still published, but Braga is no longer an accepted location
    yaml_text = client.get("/api/config").json()["yaml"]
    new_yaml = yaml_text.replace("locations_primary: [braga]", "locations_primary: [lisboa]")
    new_yaml = new_yaml.replace("locations: [braga, guimaraes", "locations: [lisboa, guimaraes")
    assert client.put("/api/config", json={"yaml": new_yaml}).status_code == 200
    client.post("/api/refresh")

    titles = [j["title"] for j in client.get("/api/jobs").json()]
    assert titles == ["Junior Data Engineer"]  # only the one you applied to stays visible


def test_config_roundtrip_and_validation(client):
    data = client.get("/api/config").json()
    assert "BoschGroup" in data["yaml"]
    assert data["keys"] == {"ITJOBS_API_KEY": False, "GEMINI_API_KEY": False, "ANTHROPIC_API_KEY": False}

    bad = client.put("/api/config", json={"yaml": "search: [1, 2"})
    assert bad.status_code == 400 and "YAML" in bad.json()["detail"]
    bad = client.put("/api/config", json={"yaml": "search: {locations: [braga]}\nsources: {monster: []}"})
    assert bad.status_code == 400 and "desconhecida" in bad.json()["detail"]
    bad = client.put("/api/config", json={"yaml": data["yaml"].replace("provider: gemini", "provider: openai")})
    assert bad.status_code == 400 and "provider" in bad.json()["detail"]

    new_yaml = re.sub(r"max_age_days: \d+", "max_age_days: 30", data["yaml"])
    assert client.put("/api/config", json={"yaml": new_yaml}).status_code == 200
    assert "max_age_days: 30" in client.get("/api/config").json()["yaml"]


def test_llm_scores_new_jobs(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"  # the Claude path (Gemini has its own tests)
    config_path.write_text((ROOT / "config.example.yaml").read_text(encoding="utf-8")
                           .replace("provider: gemini", "provider: anthropic"), encoding="utf-8")

    class FakeLLM:
        class messages:
            @staticmethod
            def create(**kwargs):
                assert kwargs["model"] == "claude-haiku-5-5"
                # Haiku 5.5 thinks by default and thinking counts against max_tokens: 200 cut the JSON off
                assert kwargs["max_tokens"] >= 2000 and kwargs["output_config"] == {"effort": "low"}
                return SimpleNamespace(content=[SimpleNamespace(
                    text='{"score": 90, "reason": "Pede LLMs e Python, como a tua tese"}')])

    app = create_app(config_path=config_path, db_path=tmp_path / "t.db", refresh_kwargs={
        "fetchers": {"smartrecruiters": lambda c, e, prefilter=None: list(JOBS)},
        "client": SimpleNamespace(), "llm_client": FakeLLM()})
    tc = TestClient(app)
    tc.post("/api/refresh")
    job = tc.get("/api/jobs").json()[0]
    assert job["llm_score"] == 90
    assert job["llm_reason"].startswith("Pede LLMs")
    assert job["score"] == round(0.4 * job["kw_score"] + 0.6 * 90)


def test_index_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "JobRadar" in r.text
