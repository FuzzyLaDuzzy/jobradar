import json

import httpx
import pytest

from jobradar import gemini, message, scoring

ANSWER = {"candidates": [{"finishReason": "STOP", "content": {"role": "model", "parts": [
    {"text": "pensamento interno", "thought": True}, {"text": "Subject: Application\n\nHello"}]}}]}


def client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_generate_request_and_answer():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=ANSWER)

    text = gemini.generate("olá", "gemini-3.8-flash", system="regras", client=client(handler), api_key="segredo")
    assert text == "Subject: Application\n\nHello"  # thought parts are skipped
    request = seen[0]
    assert str(request.url) == "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent"
    # the key goes in a header, never in the URL (URLs end up in logs and error messages)
    assert request.headers["x-goog-api-key"] == "segredo" and "segredo" not in str(request.url)
    body = json.loads(request.content)
    assert body["systemInstruction"] == {"parts": [{"text": "regras"}]}
    assert body["contents"] == [{"role": "user", "parts": [{"text": "olá"}]}]
    assert body["generationConfig"]["maxOutputTokens"] >= 2000


@pytest.mark.parametrize("response,expected", [
    (httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}}), "bloqueou"),
    (httpx.Response(429, json={"error": {"code": 429, "message": "Resource exhausted"}}), "limite"),
    (httpx.Response(403, json={"error": {"code": 403, "message": "API key not valid"}}), "recusada"),
    (httpx.Response(503, json={"error": {"code": 503, "message": "high demand"}}), "muita procura"),
])
def test_generate_errors(response, expected):
    with pytest.raises(gemini.GeminiError, match=expected) as err:
        gemini.generate("olá", "gemini-3.5-flash-lite", client=client(lambda r: response), api_key="segredo")
    assert "segredo" not in str(err.value)


def test_slow_answer_is_not_called_a_connection_error():
    def handler(request):
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(gemini.GeminiError, match="demorou"):
        gemini.generate("olá", "gemini-3.8-flash", client=client(handler), api_key="k")


def gemini_cfg(cfg):
    return {**cfg, "scoring": {"llm": {"enabled": True, "provider": "gemini"}}}


def test_scoring_with_gemini(cfg, monkeypatch):
    llm_cfg = gemini_cfg(cfg)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert not scoring.llm_available(llm_cfg)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    assert scoring.llm_available(llm_cfg)

    def handler(request):
        assert request.url.path.endswith("/gemini-3.5-flash-lite:generateContent")  # cheaper model for scoring
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [
            {"text": '{"score": 80, "reason": "Pede Python e LLMs"}'}]}}]})

    from jobradar.models import Job
    job = Job(source="s", external_id="1", company="X", title="AI Engineer", location="Braga", url="u")
    assert scoring.llm_score(job, llm_cfg, client(handler)) == (80, "Pede Python e LLMs")


def test_interview_prep_with_gemini(cfg, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "PERGUNTAS TÉCNICAS..."}]}}]})

    job = {"title": "QA Analyst", "company": "Uphold", "description": "Testing"}
    assert message.interview(job, gemini_cfg(cfg), client(handler)) == "PERGUNTAS TÉCNICAS..."
    system = seen[0]["systemInstruction"]["parts"][0]["text"]
    assert "entrevista" in system and "PERGUNTAS PARA FAZERES" in system
    assert "nunca instruções" in system  # the posting is still data, not instructions
    assert "<anuncio>" in seen[0]["contents"][0]["parts"][0]["text"]


def test_message_with_gemini(cfg, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")

    def handler(request):
        assert request.url.path.endswith("/gemini-3.8-flash:generateContent")  # better model for writing
        assert "<anuncio>" in json.loads(request.content)["contents"][0]["parts"][0]["text"]
        return httpx.Response(200, json=ANSWER)

    job = {"title": "QA Analyst", "company": "Uphold", "description": "Testing"}
    assert message.write(job, gemini_cfg(cfg), client(handler)) == "Subject: Application\n\nHello"


@pytest.mark.parametrize("status", [503, 429])
def test_busy_writing_model_falls_back_to_the_light_one(cfg, monkeypatch, status):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    seen = []

    def handler(request):
        seen.append(request.url.path.split("/")[-1])
        if "gemini-3.8-flash" in request.url.path:
            return httpx.Response(status, json={"error": {"code": status, "message": "high demand"}})
        return httpx.Response(200, json=ANSWER)

    job = {"title": "QA Analyst", "company": "Uphold", "description": "Testing"}
    assert message.write(job, gemini_cfg(cfg), client(handler)) == "Subject: Application\n\nHello"
    assert seen == ["gemini-3.8-flash:generateContent", "gemini-3.5-flash-lite:generateContent"]


def test_other_errors_are_not_retried(cfg, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    seen = []

    def handler(request):
        seen.append(request.url.path)
        return httpx.Response(403, json={"error": {"code": 403, "message": "API key not valid"}})

    job = {"title": "QA Analyst", "company": "Uphold", "description": "Testing"}
    with pytest.raises(gemini.GeminiError, match="recusada"):
        message.write(job, gemini_cfg(cfg), client(handler))
    assert len(seen) == 1  # a refused key is refused by every model
