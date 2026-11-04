"""The phone app (android/main.py): any other app on the phone can reach 127.0.0.1, so there the API
answers only the app's own window, which opened /?k=<token> once and has the cookie."""

import sys
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from jobradar import scoring
from jobradar.app import create_app

ROOT = Path(__file__).resolve().parents[1]


def client(tmp_path, token=None, llm_client=None):
    (tmp_path / "config.yaml").write_text((ROOT / "config.example.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    app = create_app(config_path=tmp_path / "config.yaml", db_path=tmp_path / "t.db", env_path=tmp_path / ".env",
                     token=token, llm_client=llm_client)
    return TestClient(app), app


def test_on_the_phone_only_the_apps_window_reaches_the_api(tmp_path):
    tc, app = client(tmp_path, token="s3cret")
    assert tc.get("/api/jobs").status_code == 403  # another app on the phone
    assert tc.put("/api/keys", json={"GEMINI_API_KEY": "x"}).status_code == 403
    assert not (tmp_path / ".env").exists()
    page = tc.get("/?k=wrong")
    assert page.status_code == 200 and "set-cookie" not in page.headers and app.state.opened.is_set()
    assert tc.get("/static/app.js").status_code == 200  # the page itself isn't secret

    opened = tc.get("/?k=s3cret", follow_redirects=False)  # the app's window, once
    assert opened.status_code == 303 and opened.headers["location"] == "/"
    cookie = opened.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert tc.get("/api/jobs").json() == []


def test_the_page_is_checked_again_after_an_update(tmp_path):
    tc, _ = client(tmp_path)
    for path in ("/", "/static/app.js", "/static/style.css"):
        assert tc.get(path).headers["cache-control"] == "no-cache", path
    assert "cache-control" not in tc.get("/api/jobs").headers


def test_on_a_computer_there_is_no_token(tmp_path):
    tc, _ = client(tmp_path)
    assert tc.get("/api/jobs").json() == []
    assert tc.get("/?k=anything").status_code == 200


def test_the_ai_buttons_work_without_the_anthropic_package(tmp_path, monkeypatch):
    """The phone app carries Gemini only: importing anthropic there made every AI button answer 500."""
    monkeypatch.setitem(sys.modules, "anthropic", None)  # "import anthropic" fails now, as on the phone
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    answer = {"candidates": [{"content": {"parts": [{"text": "Subject: Hello"}]}, "finishReason": "STOP"}]}
    gemini = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=answer)))
    tc, _ = client(tmp_path, llm_client=gemini)
    uid = tc.post("/api/jobs", json={"title": "QA Analyst", "company": "Uphold", "url": "https://x.pt/1"}).json()["uid"]
    assert tc.post(f"/api/jobs/{uid}/message").json() == {"text": "Subject: Hello"}
    assert [c["provider"] for c in scoring.ai_choices([])] == ["gemini"]  # no Claude to pick in the settings
