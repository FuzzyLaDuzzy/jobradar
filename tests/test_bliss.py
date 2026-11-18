"""Bliss, the assistant: what it knows, how it answers, its routes and its voice."""

import base64
import io
import json
import wave

import httpx
import pytest

from jobradar import gemini


def gemini_audio(data: bytes, mime="audio/wav"):
    return {"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": mime,
                                                                   "data": base64.b64encode(data).decode()}}]}}]}


def test_speak_returns_the_wav_gemini_sends(make_client):
    wav = b"RIFF" + b"\0" * 40
    seen = []
    client = make_client(lambda r: seen.append(r) or httpx.Response(200, json=gemini_audio(wav)))
    assert gemini.speak("Olá!", client=client, api_key="segredo") == wav
    body = json.loads(seen[0].content)
    assert "gemini-3.8-flash-lite-tts:generateContent" in str(seen[0].url)
    assert body["contents"] == [{"parts": [{"text": "Olá!"}]}]  # only the text: the model reads instructions aloud
    assert "systemInstruction" not in body
    assert body["generationConfig"]["responseModalities"] == ["AUDIO"]
    assert body["generationConfig"]["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"] == "Charon"
    assert seen[0].headers["x-goog-api-key"] == "segredo" and "segredo" not in str(seen[0].url)


def test_speak_wraps_raw_pcm_in_a_wav(make_client):
    pcm = b"\x01\x00" * 2400
    client = make_client(lambda r: httpx.Response(200, json=gemini_audio(pcm, "audio/L16;codec=pcm;rate=24000")))
    with wave.open(io.BytesIO(gemini.speak("Olá", client=client, api_key="k"))) as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()) == (24000, 1, 2, 2400)


def test_speak_out_of_free_quota(make_client):
    client = make_client(lambda r: httpx.Response(429, json={"error": {"message": "quota"}}))
    with pytest.raises(gemini.GeminiError) as err:
        gemini.speak("Olá", client=client, api_key="k")
    assert err.value.status == 429
