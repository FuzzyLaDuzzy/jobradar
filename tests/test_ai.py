"""⚙ The AI model: Google's list of Gemini models (or a short one), Claude, and the choice saved in config.yaml."""

import shutil
from pathlib import Path

import httpx
import pytest
import yaml
from fastapi.testclient import TestClient

from jobradar import config, gemini, scoring
from jobradar.app import create_app

ROOT = Path(__file__).resolve().parents[1]


def test_choices_newest_first_and_claude_last():
    choices = scoring.ai_choices(["gemini-2.5-flash", "gemini-3.8-flash", "gemini-3.1-pro-preview", "gemini-3.8-flash-lite",
                                  "gemini-3-flash-preview", "gemini-2.5-computer-use-preview-10-2025", "gemma-4-31b-it"])
    assert [c["id"] for c in choices] == [
        "gemini:gemini-3.8-flash-lite", "gemini:gemini-3.8-flash", "gemini:gemini-3.5-flash-lite",
        "gemini:gemini-3.1-pro-preview", "gemini:gemini-3-flash-preview",  # "3" is 3.0
        "gemini:gemini-2.5-flash", "anthropic"]  # not the computer-use or Gemma ones
    assert [c["label"] for c in choices][:4] == ["Gemini 3.8 Flash Lite", "Gemini 3.8 Flash", "Gemini 3.5 Flash Lite",
                                                 "Gemini 3.1 Pro (preview)"]
    assert [c["id"] for c in choices if c["default"]] == ["gemini:gemini-3.5-flash-lite"]  # always offered
    assert choices[-1]["model"] == "claude-haiku-5-5" and choices[-1]["message_model"] == "claude-opus-5-5"


def test_unknown_choices():
    assert scoring.ai_choice("gemini:gpt-5") is None
    assert scoring.ai_choice("openai:gpt-5") is None
    assert scoring.ai_choice("gemini:gemini-3.8-flash; rm -rf") is None


def test_google_list_of_models():
    answer = {"models": [
        {"name": "models/gemini-3.5-flash-lite", "supportedGenerationMethods": ["generateContent", "countTokens"]},
        {"name": "models/gemini-3.8-flash", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-embedding-001", "supportedGenerationMethods": ["embedContent"]},
        {"name": "models/gemini-3.5-transcribe", "supportedGenerationMethods": ["generateContent"]}]}
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=answer)

    models = gemini.list_models(httpx.Client(transport=httpx.MockTransport(handler)), api_key="segredo")
    assert models == ["gemini-3.5-flash-lite", "gemini-3.8-flash"]
    assert seen[0].headers["x-goog-api-key"] == "segredo" and "segredo" not in str(seen[0].url)
    refused = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(403)))
    assert gemini.list_models(refused, api_key="x") == []  # the short list is used instead


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setattr(gemini, "list_models", lambda: ["gemini-3.8-flash", "gemini-3.5-flash-lite"])
    path = tmp_path / "config.yaml"
    shutil.copy(ROOT / "config.example.yaml", path)
    tc = TestClient(create_app(config_path=path, db_path=tmp_path / "t.db"))
    tc.config_path = path
    return tc


def test_choose_a_model_in_settings(client):
    data = client.get("/api/ai").json()
    assert data["current"] == "gemini:gemini-3.5-flash-lite"  # the default
    assert [c["id"] for c in data["choices"]] == ["gemini:gemini-3.8-flash", "gemini:gemini-3.5-flash-lite", "anthropic"]

    before = client.config_path.read_text(encoding="utf-8")
    assert client.put("/api/ai", json={"choice": "gemini:gemini-3.8-flash"}).json() == {"current": "gemini:gemini-3.8-flash"}
    after = client.config_path.read_text(encoding="utf-8")
    llm = yaml.safe_load(after)["scoring"]["llm"]
    assert (llm["provider"], llm["model"], llm["message_model"]) == ("gemini", "gemini-3.8-flash", "gemini-3.8-flash")
    # only two lines more: every comment stays, the last value's one on its own line
    assert [line for line in after.splitlines() if line not in before.splitlines()] == [
        "    model: gemini-3.8-flash", "    message_model: gemini-3.8-flash"]
    assert client.get("/api/ai").json()["current"] == "gemini:gemini-3.8-flash"

    client.put("/api/ai", json={"choice": "anthropic"})
    llm = config.load(client.config_path)["scoring"]["llm"]
    assert (llm["provider"], llm["model"], llm["message_model"]) == ("anthropic", "claude-haiku-5-5", "claude-opus-5-5")
    assert client.get("/api/ai").json()["current"] == "anthropic"

    assert client.put("/api/ai", json={"choice": "gemini:gpt-5"}).status_code == 400
    assert client.put("/api/ai", json={"choice": ""}).status_code == 422


def test_nested_section_must_exist(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("search:\n  locations: [braga]\nsources:\n  landingjobs:\n    - feed: https://landing.jobs/feed\n",
                    encoding="utf-8")
    with pytest.raises(config.ConfigError):
        config.update({("scoring.llm", "model"): "gemini-3.8-flash"}, path)
