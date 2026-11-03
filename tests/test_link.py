"""+ Add job from a link: the schema.org JobPosting careers sites embed, else the page's title."""

import json

import httpx
import pytest

from jobradar import link

POSTING = {"@context": "https://schema.org", "@type": "JobPosting", "title": "Junior Backend Developer",
           "datePosted": "2026-10-28T09:00:00Z", "description": "&lt;p&gt;Python and SQL.&lt;/p&gt;",
           "hiringOrganization": {"@type": "Organization", "name": "Acme"},
           "jobLocation": [{"@type": "Place", "address": {"addressLocality": "Braga", "addressCountry": "PT"}}]}


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
