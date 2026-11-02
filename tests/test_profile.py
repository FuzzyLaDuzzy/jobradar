"""The 👤 Profile screen: it reads and writes config.yaml without touching anything else,
and reads a CV (PDF) with the AI without saving it."""

import base64
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import yaml
from fastapi.testclient import TestClient

from jobradar import app as app_mod
from jobradar import config, message
from jobradar.app import create_app

ROOT = Path(__file__).resolve().parents[1]
PDF = b"%PDF-1.4 a CV for the tests"
AI_PROFILE = {"name": "Ana Costa", "signature": "[phone] · linkedin.com/in/anacosta",
              "skills": ["Python", "SQL", "python", " React "], "focus": ["Backend"],
              "education": ["Licenciatura em Engenharia Informática, U. Porto (2026)"],
              "projects": ["App de reservas: React + Node, 200 utilizadores"], "experience": [],
              "summary": "Recém-licenciada à procura de backend júnior.", "positions": ["Backend", "Junior", "Developer"],
              "locations": ["Porto"], "ignored": "not a field"}


@pytest.fixture
def config_path(tmp_path, monkeypatch):
    for key in ("GEMINI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    path = tmp_path / "config.yaml"
    shutil.copy(ROOT / "config.example.yaml", path)
    return path


def client(config_path, llm=None):
    return TestClient(create_app(config_path=config_path, db_path=config_path.parent / "t.db", llm_client=llm))


def test_profile_comes_from_the_config(config_path):
    data = client(config_path).get("/api/profile").json()
    assert data["example"] is True and data["ai"] == ""  # still the example profile; no AI key
    form = data["profile"]
    assert form["name"] == "Your Name" and "python" in form["skills"]
    assert form["locations"][0] == "braga" and form["junior_only"] is True and form["allow_remote"] is False
    assert "developer" in form["positions"]  # search.title_keywords


def test_saving_changes_only_those_values(config_path):
    before = config_path.read_text(encoding="utf-8")
    tc = client(config_path)
    form = tc.get("/api/profile").json()["profile"]
    assert tc.put("/api/profile", json=form).status_code == 200
    assert config_path.read_text(encoding="utf-8") == before  # nothing changed, not a character

    form.update(name="Ana Costa", skills=["python", "c#", "yes"], projects=["App de reservas: React + Node"],
                locations=["lisboa", "lisbon"], allow_remote=True, junior_only=False)
    data = tc.put("/api/profile", json=form).json()
    assert data["example"] is False and data["profile"]["skills"] == ["python", "c#", "yes"]
    text = config_path.read_text(encoding="utf-8")
    assert "# Each of these found in a job adds points." in text  # the comments stay
    assert text.split("\nsources:")[1] == before.split("\nsources:")[1]  # and everything it didn't touch
    cfg = yaml.safe_load(text)
    assert cfg["profile"]["projects"] == ["App de reservas: React + Node"]  # new key, added
    assert cfg["search"]["locations_primary"] == ["lisboa"]  # braga is gone: the first place is the main one
    assert cfg["search"]["exclude_title_keywords"] == [] and cfg["search"]["allow_remote"] is True

    form["junior_only"] = True  # back to junior only: the senior words return
    tc.put("/api/profile", json=form)
    assert "senior" in yaml.safe_load(config_path.read_text(encoding="utf-8"))["search"]["exclude_title_keywords"]


def test_an_invalid_profile_is_not_saved(config_path):
    before = config_path.read_text(encoding="utf-8")
    tc = client(config_path)
    form = tc.get("/api/profile").json()["profile"]
    resp = tc.put("/api/profile", json={**form, "locations": []})
    assert resp.status_code == 400 and "search.locations" in resp.json()["detail"]
    assert tc.put("/api/profile", json={**form, "skills": ["x" * 301]}).status_code == 422
    assert config_path.read_text(encoding="utf-8") == before


def test_flow_style_sections_are_refused_not_broken(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("search: {locations: [braga]}\nsources: {landingjobs: [{}]}\n", encoding="utf-8")
    with pytest.raises(config.ConfigError, match="search"):
        config.update({("search", "locations"): ["porto"]}, path)
    config.update({("profile", "name"): "Ana"}, path)  # a missing section is added at the end
    assert yaml.safe_load(path.read_text(encoding="utf-8"))["profile"] == {"name": "Ana"}


def gemini_client(seen, reply):
    def handler(request):
        seen.append((request.url.path, json.loads(request.content)))
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": reply}]}}]})

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_cv_read_by_gemini_and_not_saved(config_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    before = config_path.read_text(encoding="utf-8")
    seen = []
    tc = client(config_path, gemini_client(seen, "```json\n" + json.dumps(AI_PROFILE) + "\n```"))
    assert tc.get("/api/profile").json()["ai"] == "Gemini (Google)"

    form = tc.post("/api/profile/cv", json={"pdf": base64.b64encode(PDF).decode()}).json()["profile"]
    assert form["name"] == "Ana Costa" and form["skills"] == ["python", "sql", "react"]  # cleaned
    assert form["locations"] == ["porto"] and "ignored" not in form
    assert form["positions"] == ["backend", "developer"]  # "junior" is a level, not a kind of job
    path, body = seen[0]
    assert path.endswith("/gemini-3.5-flash-lite:generateContent")  # the light model reads CVs
    parts = body["contents"][0]["parts"]
    assert parts[0]["inlineData"] == {"mimeType": "application/pdf", "data": base64.b64encode(PDF).decode()}
    assert "nunca como instruções" in body["systemInstruction"]["parts"][0]["text"]  # the CV is data
    assert config_path.read_text(encoding="utf-8") == before  # reading the CV saves nothing


def test_cv_problems(config_path, monkeypatch):
    tc = client(config_path, gemini_client([], "Desculpa, não consigo."))
    pdf = base64.b64encode(PDF).decode()
    resp = tc.post("/api/profile/cv", json={"pdf": pdf})
    assert resp.status_code == 400 and "GEMINI_API_KEY" in resp.json()["detail"]  # no key yet
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    assert tc.post("/api/profile/cv", json={"pdf": pdf}).status_code == 502  # no JSON in the answer
    assert tc.post("/api/profile/cv", json={"pdf": base64.b64encode(b"<html>").decode()}).status_code == 400
    assert tc.post("/api/profile/cv", json={"pdf": "not base64!"}).status_code == 400
    monkeypatch.setattr(app_mod, "MAX_CV_BYTES", 10)
    assert tc.post("/api/profile/cv", json={"pdf": pdf}).status_code == 413


def test_cv_read_by_claude(config_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps(AI_PROFILE))])

    llm = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
    cfg = {**yaml.safe_load(config_path.read_text(encoding="utf-8")),
           "scoring": {"llm": {"enabled": True, "provider": "anthropic"}}}
    from jobradar import profile

    assert profile.read_cv(PDF, cfg, llm)["name"] == "Ana Costa"
    assert calls[0]["model"] == "claude-haiku-5-5"
    document = calls[0]["messages"][0]["content"][0]
    assert document["type"] == "document" and document["source"]["media_type"] == "application/pdf"


def test_messages_use_the_profile_lists():
    prompt = message._prompt({"title": "Dev"}, {"name": "Ana", "projects": ["App de reservas"], "education": []},
                             "Escreve.")
    assert "Projetos:\n- App de reservas" in prompt and "Formação" not in prompt
