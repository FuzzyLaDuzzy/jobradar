"""Google Gemini through its REST API, with a (free) key from Google AI Studio.

  POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent
The key goes in the x-goog-api-key header, never in the URL, so it can't end up in
logs or error messages. Plain httpx, which the project already uses: no extra SDK.
"""

from __future__ import annotations

import base64
import os

import httpx

from .i18n import t

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiError(RuntimeError):
    """Gemini answered with an error, blocked the request or returned no text."""


def _fail(resp: httpx.Response) -> GeminiError:
    if resp.status_code == 429:
        return GeminiError(t("Atingiste o limite do plano gratuito do Gemini. Tenta daqui a uns minutos."))
    if resp.status_code == 503:  # "The model is overloaded": it passes on its own
        return GeminiError(t("O Gemini está com muita procura neste momento. Tenta daqui a uns minutos."))
    if resp.status_code in (401, 403):
        return GeminiError(t("A GEMINI_API_KEY foi recusada. Cria uma chave nova no Google AI Studio."))
    try:
        detail = resp.json()["error"]["message"]
    except (ValueError, KeyError, TypeError):
        detail = ""
    return GeminiError(t("A API do Gemini respondeu com o erro {code}. {detail}", code=resp.status_code, detail=detail).strip())


def generate(prompt: str, model: str, system: str = "", max_tokens: int = 8192,
             client: httpx.Client | None = None, api_key: str | None = None, pdf: bytes | None = None) -> str:
    parts: list[dict] = [{"text": prompt}]
    if pdf:  # Gemini reads the PDF itself (a CV): sent inline, base64
        parts.insert(0, {"inlineData": {"mimeType": "application/pdf", "data": base64.b64encode(pdf).decode()}})
    body: dict = {
        "contents": [{"role": "user", "parts": parts}],
        # thinking counts against this limit, so leave plenty of room for the answer
        "generationConfig": {"maxOutputTokens": max_tokens},
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    own = client is None
    # long answers (interview prep) take minutes: Flash thinks before writing
    client = client or httpx.Client(timeout=httpx.Timeout(300.0, connect=10.0))
    try:
        resp = client.post(API.format(model=model), json=body,
                           headers={"x-goog-api-key": api_key or os.environ.get("GEMINI_API_KEY", "")})
    except httpx.TimeoutException as exc:
        raise GeminiError(t("O Gemini demorou demasiado a responder. Tenta outra vez.")) from exc
    except httpx.HTTPError as exc:
        raise GeminiError(t("Sem ligação à API do Gemini.")) from exc
    finally:
        if own:
            client.close()
    if resp.is_error:
        raise _fail(resp)

    data = resp.json()
    candidates = data.get("candidates") or []
    if not candidates:
        reason = (data.get("promptFeedback") or {}).get("blockReason", "?")
        raise GeminiError(t("O Gemini bloqueou o pedido ({reason}).", reason=reason))
    parts = (candidates[0].get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
    if not text:
        raise GeminiError(t("O Gemini não devolveu texto ({reason}).", reason=candidates[0].get("finishReason", "?")))
    return text
