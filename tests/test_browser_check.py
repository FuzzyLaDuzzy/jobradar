"""A site that answers with a bot check (Cloudflare's "Just a moment...", "Security Check") instead of its data:
JobRadar does not get around it, and says so plainly instead of "HTTP 403" or "429 Too Many Requests"."""

import httpx
import pytest

from jobradar.sources.base import BrowserCheck, make_client


def client_answering(status: int, body: str, headers: dict | None = None) -> httpx.Client:
    return make_client(transport=httpx.MockTransport(lambda request: httpx.Response(status, text=body,
                                                                                    headers=headers or {})))


@pytest.mark.parametrize("status,body,headers", [
    (403, "<title>Just a moment...</title>", {"server": "cloudflare", "cf-mitigated": "challenge"}),  # ITJobs
    (429, "<h1>Security Check</h1> Enable JavaScript and cookies to continue", {"server": "cloudflare"}),  # Workday
])
def test_a_browser_check_is_named_as_such(status, body, headers):
    with pytest.raises(BrowserCheck) as raised:
        client_answering(status, body, headers).get("https://api.itjobs.pt/job/search.json")
    message = str(raised.value)
    assert "api.itjobs.pt" in message and "verificação de browser" in message
    assert isinstance(raised.value, RuntimeError)  # an expected error: shown on the source, without a traceback


def test_an_ordinary_refusal_is_left_to_the_source():
    response = client_answering(403, '{"error": "Invalid API Key"}').get("https://api.itjobs.pt/job/search.json")
    assert response.status_code == 403
