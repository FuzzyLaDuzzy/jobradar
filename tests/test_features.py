"""The ✂ cut jobs, the CSV export, the salary on each job and "+ Add job" from a link, through the API."""

import csv
import io
import shutil
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from jobradar import app as app_module
from jobradar import i18n, link
from jobradar.app import create_app
from jobradar.filters import reason_label
from jobradar.models import Job

ROOT = Path(__file__).resolve().parents[1]

JOBS = [
    Job(source="smartrecruiters:BoschGroup", external_id="1", company="Bosch", title="Junior AI Software Engineer",
        location="Braga, Portugal", url="https://jobs.smartrecruiters.com/BoschGroup/1", posted_at="2026-10-28",
        description="Python e LLM. Salário: 1.200€ - 1.500€ brutos por mês."),
    Job(source="smartrecruiters:BoschGroup", external_id="2", company="Bosch", title="Senior Embedded Engineer",
        location="Braga, Portugal", url="https://jobs.smartrecruiters.com/BoschGroup/2", posted_at="2026-10-28"),
]


@pytest.fixture
def client(tmp_path):
    config_path = tmp_path / "config.yaml"
    shutil.copy(ROOT / "config.example.yaml", config_path)
    fetchers = {"smartrecruiters": lambda c, e, prefilter=None: list(JOBS)}
    app = create_app(config_path=config_path, db_path=tmp_path / "test.db",
                     refresh_kwargs={"fetchers": fetchers, "client": SimpleNamespace()})
    return TestClient(app)


def test_cut_jobs_and_why(client):
    client.post("/api/refresh")
    cut = client.get("/api/cut").json()
    assert [(c["title"], c["reason"], c["category"]) for c in cut] == [
        ("Senior Embedded Engineer", "título sénior (senior)", "título sénior")]
    assert cut[0]["url"] == "https://jobs.smartrecruiters.com/BoschGroup/2"
    client.post("/api/refresh")
    assert len(client.get("/api/cut").json()) == 1  # each search replaces its source's list


def test_cut_reasons_in_english(monkeypatch):
    monkeypatch.setattr(i18n, "language", "en")
    assert reason_label("título sénior (lead)") == "senior title (lead)"
    assert reason_label("fora da zona") == "outside your area"


def test_salary_on_each_job(client):
    client.post("/api/refresh")
    job = client.get("/api/jobs").json()[0]
    assert job["salary"] == {"text": "1.200€ - 1.500€ brutos por mês", "min": 1200, "max": 1500, "period": "month"}


def test_export_csv(client):
    client.post("/api/refresh")
    uid = client.get("/api/jobs").json()[0]["uid"]
    client.patch(f"/api/jobs/{uid}", json={"status": "candidatei"})
    client.post("/api/jobs", json={"title": "Data Engineer", "company": "Acme", "url": "https://x.pt/1",
                                   "notes": "=HYPERLINK(\"https://evil.example\")"})
    resp = client.get("/api/export.csv")
    assert resp.headers["content-disposition"] == 'attachment; filename="jobradar-candidaturas.csv"'
    text = resp.content.decode("utf-8")
    assert text.startswith("﻿Estado;Empresa;Vaga;")  # the BOM, so Excel reads the accents
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿")), delimiter=";"))
    assert rows[1][:5] == ["Candidatei", "Bosch", "Junior AI Software Engineer", "Braga, Portugal",
                           "1.200€ - 1.500€ brutos por mês"]
    assert rows[2][:3] == ["Guardada", "Acme", "Data Engineer"]
    assert rows[2][10] == "'=HYPERLINK(\"https://evil.example\")"  # a formula stays text in Excel
    assert len(rows) == 3  # the job you never touched isn't there


def test_add_job_from_a_link(client, monkeypatch):
    page = ('<script type="application/ld+json">{"@type": "JobPosting", "title": "QA Engineer", '
            '"hiringOrganization": {"name": "Acme"}, "datePosted": "2026-10-30", "description": "Testes"}</script>')
    monkeypatch.setattr(app_module, "make_client",
                        lambda: httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=page))))
    monkeypatch.setattr(link, "_resolve", lambda host: "93.184.215.14")  # careers.acme.pt is made up
    job = client.post("/api/jobs/from-url", json={"url": "https://careers.acme.pt/qa"}).json()
    assert (job["title"], job["company"], job["posted_at"]) == ("QA Engineer", "Acme", "2026-10-30")
    saved = client.post("/api/jobs", json={k: job[k] for k in ("title", "company", "url", "description", "posted_at")}).json()
    assert (saved["description"], saved["posted_at"], saved["status"]) == ("Testes", "2026-10-30", "guardada")

    assert client.post("/api/jobs/from-url", json={"url": "javascript:alert(1)"}).status_code == 422
    refused = client.post("/api/jobs/from-url", json={"url": "https://www.linkedin.com/jobs/view/1"})
    assert refused.status_code == 400 and "à mão" in refused.json()["detail"]


def test_sources_that_look_broken(tmp_path):
    from jobradar.db import Database
    db = Database(tmp_path / "t.db")

    def run(source, status, fetched, message=""):
        db.add_run(source=source, started_at="2026-11-03T09:00:00", finished_at="2026-11-03T09:01:00",
                   fetched=fetched, kept=0, new=0, status=status, message=message)

    for _ in range(3):
        run("lever:acme", "ok", 40)       # fine
        run("workday:old", "ok", 120)     # used to bring jobs...
        run("ey", "ok", 0)                # never did
    for _ in range(3):
        run("lever:acme", "ok", 38)
        run("workday:old", "ok", 0)       # ...and stopped
        run("ey", "ok", 0)
        run("itjobs", "skipped", 0, "Falta ITJOBS_API_KEY")  # no key: not broken
    run("teamtailor:x", "ok", 5)
    for _ in range(3):
        run("teamtailor:x", "error", 0, "404 Not Found")
    health = db.source_health()
    assert health == [
        {"source": "ey", "kind": "never", "runs": 6, "before": 0},
        {"source": "teamtailor:x", "kind": "error", "runs": 3, "message": "404 Not Found"},
        {"source": "workday:old", "kind": "empty", "runs": 3, "before": 120}]
    assert db.source_health({"lever:acme", "ey"}) == [health[0]]  # only the sources still in the config
    # the sources line too: a source taken out of the config stops showing
    assert [r["source"] for r in db.last_runs({"lever:acme", "ey"})] == ["ey", "lever:acme"]
    assert len(db.last_runs()) == 5


def test_health_endpoint(client):
    assert client.get("/api/health").json() == []  # no searches yet


def test_your_choices_as_examples(tmp_path):
    from jobradar.db import Database
    db = Database(tmp_path / "t.db")
    for job in JOBS + [Job(source="manual", external_id="9", company="Gamma", title="SAP Consultant", location="", url="")]:
        db.upsert(job, 50, [], {}, "2026-11-03T09:00:00+00:00")
    db.update(JOBS[0].uid, status="candidatei")
    db.update("manual:9", status="descartada")
    assert db.decision_examples() == {"liked": ["Junior AI Software Engineer (Bosch)"], "disliked": ["SAP Consultant (Gamma)"]}


def test_filter_change_from_the_cut_tab(client):
    client.post("/api/refresh")
    cut = client.get("/api/cut").json()[0]
    assert (cut["kind"], cut["word"]) == ("título sénior", "senior")  # what the suggestion needs
    before = client.get("/api/config").json()["yaml"]

    done = client.post("/api/filters", json={"action": "remove", "field": "exclude_title_keywords", "word": "Senior"}).json()
    assert "senior" not in done["values"] and "lead" in done["values"]
    client.post("/api/filters", json={"action": "add", "field": "locations", "word": "Lousado"})
    client.post("/api/filters", json={"action": "add", "field": "locations", "word": "lousado"})  # already there
    after = client.get("/api/config").json()["yaml"]
    import yaml as _yaml
    search = _yaml.safe_load(after)["search"]
    assert search["locations"].count("lousado") == 1 and "senior" not in search["exclude_title_keywords"]
    assert after.count("#") == before.count("#")  # the comments stay

    client.post("/api/refresh")  # from the next search on, that job is kept
    assert "Senior Embedded Engineer" in [j["title"] for j in client.get("/api/jobs").json()]

    # only taking words out of the exclusions, and only adding to the area or the kind of job
    assert client.post("/api/filters", json={"action": "add", "field": "exclude_keywords", "word": "x"}).status_code == 400
    assert client.post("/api/filters", json={"action": "remove", "field": "locations", "word": "braga"}).status_code == 400
    assert client.post("/api/filters", json={"action": "add", "field": "profile", "word": "x"}).status_code == 422
    assert client.post("/api/filters", json={"action": "add", "field": "locations", "word": "a\nscoring: {}"}).status_code == 422
