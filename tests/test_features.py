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
