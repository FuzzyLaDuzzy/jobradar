"""+ Add job from a link: the schema.org JobPosting careers sites embed, else the page's title."""

import json

import httpx
import pytest

from jobradar import link

POSTING = {"@context": "https://schema.org", "@type": "JobPosting", "title": "Junior Backend Developer",
           "datePosted": "2026-10-28T09:00:00Z", "description": "&lt;p&gt;Python and SQL.&lt;/p&gt;",
           "hiringOrganization": {"@type": "Organization", "name": "Acme"},
           "jobLocation": [{"@type": "Place", "address": {"addressLocality": "Braga", "addressCountry": "PT"}}]}


@pytest.fixture(autouse=True)
def public_names(monkeypatch):
    """The made-up hosts below don't exist: every name counts as public, unless a test says otherwise."""
    monkeypatch.setattr(link, "_is_public", lambda host: True)


def page(*blocks, head=""):
    scripts = "".join(f'<script type="application/ld+json">{json.dumps(b)}</script>' for b in blocks)
    return f"<html><head>{head}{scripts}</head><body>…</body></html>"


def client(text, status=200):
    return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(status, text=text)))


def test_reads_the_job_posting():
    job = link.read("https://careers.acme.pt/jobs/42", client(page({"@type": "Organization"}, POSTING)))
    assert job == {"title": "Junior Backend Developer", "company": "Acme", "location": "Braga, PT",
                   "posted_at": "2026-10-28", "description": "Python and SQL.", "url": "https://careers.acme.pt/jobs/42"}


def test_posting_inside_a_graph():
    data = {"@context": "https://schema.org", "@graph": [{"@type": "WebPage"}, POSTING | {"jobLocationType": "TELECOMMUTE"}]}
    assert link.read("https://x.pt/1", client(page(data)))["location"] == "Braga, PT, Remote"


def test_page_without_a_posting_uses_its_title():
    head = '<meta property="og:title" content="Data Engineer · Acme"><meta name="description" content="Join us in Braga">'
    job = link.read("https://x.pt/2", client(page(head=head)))
    assert (job["title"], job["description"], job["company"]) == ("Data Engineer · Acme", "Join us in Braga", "")


@pytest.mark.parametrize("url", ["https://www.linkedin.com/jobs/view/1", "https://pt.indeed.com/viewjob?jk=1"])
def test_sites_that_forbid_it_are_not_opened(url):
    seen = []
    with pytest.raises(link.LinkError, match="à mão"):
        link.read(url, httpx.Client(transport=httpx.MockTransport(lambda r: seen.append(r) or httpx.Response(200))))
    assert seen == []


def test_errors():
    with pytest.raises(link.LinkError, match="abrir"):
        link.read("https://x.pt/404", client("", status=404))
    with pytest.raises(link.LinkError, match="Não encontrei"):
        link.read("https://x.pt/empty", client("<html><body>nada</body></html>"))


def test_local_and_private_addresses_are_not_opened(monkeypatch):
    monkeypatch.undo()  # the real check: these are IPs, nothing to look up
    seen = []
    any_page = httpx.Client(transport=httpx.MockTransport(lambda r: seen.append(r) or httpx.Response(200, text="x")))
    for url in ("http://127.0.0.1:8000/api/keys", "http://192.168.1.1/", "http://169.254.169.254/latest/meta-data/"):
        with pytest.raises(link.LinkError, match="local ou privado"):
            link.read(url, any_page)
    assert seen == []


def test_every_redirect_hop_is_checked(monkeypatch):
    monkeypatch.setattr(link, "_is_public", lambda host: host != "intranet.local")
    hops = []

    def handler(request):
        hops.append(request.url.host)
        return httpx.Response(302, headers={"location": "http://intranet.local/admin"})

    with pytest.raises(link.LinkError, match="local ou privado"):
        link.read("https://short.link/abc", httpx.Client(transport=httpx.MockTransport(handler)))
    assert hops == ["short.link"]  # the private address is never asked for


def test_a_redirect_to_a_public_page_is_followed():
    def handler(request):
        if request.url.path == "/abc":
            return httpx.Response(301, headers={"location": "https://careers.acme.pt/jobs/42"})
        return httpx.Response(200, text=page(POSTING))

    job = link.read("https://short.link/abc", httpx.Client(transport=httpx.MockTransport(handler)))
    assert (job["title"], job["url"]) == ("Junior Backend Developer", "https://careers.acme.pt/jobs/42")


def test_a_page_too_big_stops_being_read(monkeypatch):
    monkeypatch.setattr(link, "MAX_BYTES", 1000)
    with pytest.raises(link.LinkError, match="grande demais"):  # said up front
        link.read("https://x.pt/big", httpx.Client(transport=httpx.MockTransport(
            lambda r: httpx.Response(200, headers={"content-length": "5000"}, content=b"x" * 10))))
    with pytest.raises(link.LinkError, match="grande demais"):  # or only found out while reading
        link.read("https://x.pt/big", httpx.Client(transport=httpx.MockTransport(
            lambda r: httpx.Response(200, content=iter([b"x" * 600, b"x" * 600])))))
