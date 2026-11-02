"""The welcome screen saves the API keys to .env, and the app never sends them back."""

import os
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from jobradar.app import create_app

ROOT = Path(__file__).resolve().parents[1]
KEYS = ("ITJOBS_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY")


@pytest.fixture
def client(tmp_path, monkeypatch):
    for key in KEYS:  # monkeypatch puts the real values back after the test
        monkeypatch.delenv(key, raising=False)
    shutil.copy(ROOT / "config.example.yaml", tmp_path / "config.yaml")
    return TestClient(create_app(config_path=tmp_path / "config.yaml", db_path=tmp_path / "t.db",
                                 env_path=tmp_path / ".env"))


def test_keys_are_saved_and_never_returned(client, tmp_path):
    env = tmp_path / ".env"
    env.write_text("# my notes\nITJOBS_API_KEY=old-key-123\nOTHER=1\n", encoding="utf-8")
    assert client.get("/api/keys").json() == dict.fromkeys(KEYS, False)

    resp = client.put("/api/keys", json={"ITJOBS_API_KEY": " new-itjobs-key ", "GEMINI_API_KEY": "AQ.gemini_key-1"})
    assert resp.json() == {"ITJOBS_API_KEY": True, "GEMINI_API_KEY": True, "ANTHROPIC_API_KEY": False}
    assert "new-itjobs-key" not in resp.text and "gemini_key" not in resp.text
    assert env.read_text(encoding="utf-8") == (
        "# my notes\nITJOBS_API_KEY=new-itjobs-key\nOTHER=1\nGEMINI_API_KEY=AQ.gemini_key-1\n")
    assert "gemini_key" not in client.get("/api/config").text  # the settings only say which are set

    client.put("/api/keys", json={"ITJOBS_API_KEY": ""})  # an empty field keeps the key
    assert "ITJOBS_API_KEY=new-itjobs-key" in env.read_text(encoding="utf-8")


def test_used_right_away_without_a_restart(client):
    client.put("/api/keys", json={"GEMINI_API_KEY": "AQ.gemini_key-1"})
    assert os.environ["GEMINI_API_KEY"] == "AQ.gemini_key-1"


@pytest.mark.parametrize("value", ["two words here", "key\nOTHER=evil", 'quoted"key"x', "short"])
def test_a_key_that_would_break_env_is_refused(client, tmp_path, value):
    resp = client.put("/api/keys", json={"ITJOBS_API_KEY": value})
    assert resp.status_code == 422
    assert not (tmp_path / ".env").exists()


def test_new_env_starts_from_the_example(client, tmp_path):
    client.put("/api/keys", json={"ANTHROPIC_API_KEY": "sk-ant-api03-test"})
    text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "https://www.itjobs.pt/api" in text  # the example's comments came along
    assert "ANTHROPIC_API_KEY=sk-ant-api03-test" in text and "ITJOBS_API_KEY=\n" in text


def test_other_sites_cant_set_the_keys(client):
    # a page on another site needs a CORS preflight to send a PUT; it gets no permission
    resp = client.options("/api/keys", headers={"Origin": "https://evil.example",
                                                "Access-Control-Request-Method": "PUT"})
    assert resp.status_code >= 400 and "access-control-allow-origin" not in resp.headers
    # and requests that change something are refused when they come from another site
    for method, path in [("PUT", "/api/keys"), ("POST", "/api/refresh"), ("POST", "/api/jobs/x/message")]:
        resp = client.request(method, path, json={}, headers={"Origin": "https://evil.example"})
        assert resp.status_code == 403, path
    assert client.put("/api/keys", json={}, headers={"Origin": "http://testserver"}).status_code == 200


def test_other_host_names_are_refused(client):
    # DNS rebinding: evil.example pointed at 127.0.0.1 arrives with its own name as the Host
    assert client.get("/api/keys", headers={"Host": "evil.example:8000"}).status_code == 400
    assert client.get("/api/keys", headers={"Host": "127.0.0.1:8000"}).status_code == 200


def test_only_web_links_are_stored(tmp_path):
    from jobradar.db import Database
    from jobradar.models import Job

    db = Database(tmp_path / "t.db")
    db.upsert(Job(source="s", external_id="1", company="X", title="Dev", location="Lisboa",
                  url="javascript:alert(1)", logo="data:image/svg+xml,<svg onload=x>"), 0, [], {}, "2026-11-02")
    db.upsert(Job(source="s", external_id="2", company="X", title="Data Engineer", location="Lisboa",
                  url=" https://example.com/job ", logo="https://example.com/logo.png"), 0, [], {}, "2026-11-02")
    jobs = {j["external_id"]: j for j in db.all_jobs()}
    assert (jobs["1"]["url"], jobs["1"]["logo"]) == ("", "")
    assert (jobs["2"]["url"], jobs["2"]["logo"]) == ("https://example.com/job", "https://example.com/logo.png")
