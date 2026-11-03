"""Recruitee (Mercedes-Benz.io), Zoho Recruit (Edigma), Eurotux, Teamtailor (Nutrium) and Balanças Marques (with SDILAB),
from real answers cut down to a few fields."""

import html
import json

import httpx
import pytest

from jobradar.sources import balancasmarques, eurotux, recruitee, teamtailor, zohorecruit

# --- Recruitee ---------------------------------------------------------------

MBIO_OFFER = {
    "id": 2802906, "slug": "analytics-engineer-fmx", "title": "Analytics Engineer (f/m/x)",
    "company_name": "Mercedes-Benz.io GmbH", "location": "Hybrid, Lisboa, Portugal", "city": "Hybrid",
    "careers_url": "https://mbio.recruitee.com/o/analytics-engineer-fmx",
    "published_at": "2026-10-29 17:15:54 UTC", "created_at": "2026-10-29 17:01:49 UTC",
    "employment_type_code": "fulltime_permanent", "experience_code": "mid_level",
    "remote": False, "hybrid": True, "on_site": False,
    "description": "<p><strong>HEY THERE!</strong><br>We are Mercedes-Benz.io.</p>",
    "requirements": "<ul><li>SQL and dbt</li></ul>",
    # one job, two places: the `location` above only names Lisboa
    "locations": [{"city": "Hybrid", "state": "Lisboa", "country": "Portugal"},
                  {"city": "Hybrid", "state": "Braga", "country": "Portugal"}],
}


def test_recruitee_reads_every_place_of_a_job(make_client):
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, json={"offers": [MBIO_OFFER]})

    [job] = recruitee.fetch(make_client(handler), {"company": "mbio", "name": "Mercedes-Benz.io"})
    assert seen == ["https://mbio.recruitee.com/api/offers/"]  # one request, descriptions included
    assert (job.uid, job.company, job.location) == ("recruitee:mbio:2802906", "Mercedes-Benz.io", "Lisboa, Braga")
    assert (job.posted_at, job.work_model) == ("2026-10-29", "hybrid")
    assert (job.contract, job.experience) == ("Fulltime permanent", "Mid level")
    assert "We are Mercedes-Benz.io." in job.description and "SQL and dbt" in job.description
    assert job.url == "https://mbio.recruitee.com/o/analytics-engineer-fmx"


def test_recruitee_city_when_there_is_no_list():
    job = recruitee.to_job("x", {"id": 1, "title": "Dev", "city": "Braga", "locations": []})
    assert job.location == "Braga" and job.company == "x"


# --- Zoho Recruit ------------------------------------------------------------

EDIGMA_JOBS = [
    {"id": "42419000004875003", "Posting_Title": "AI Software Developer – Integrações & Automação Inteligente",
     "City": "Braga", "State": "Braga", "Country": "Portugal", "Date_Opened": "2026-10-22", "Job_Type": "Full time",
     "Work_Experience": "1-3 years", "Remote_Job": False, "Publish": True,
     "Job_Description": "<p>Sobre a função</p><p>Procuramos um(a) developer para soluções de AI.</p>"},
    {"id": "42419000004070001", "Posting_Title": "Técnico/a de Suporte (Lisboa)", "City": "Lisboa",
     "Date_Opened": "2026-04-22", "Job_Type": "Full time", "Remote_Job": False, "Publish": False,
     "Job_Description": "Não publicada"},
]
EDIGMA_PAGE = ('<html><body><input type="hidden" value="{}" id="jobs"></body></html>'
               .format(html.escape(json.dumps(EDIGMA_JOBS, ensure_ascii=False), quote=True)))


def test_zohorecruit_reads_the_jobs_in_the_page(make_client):
    jobs = zohorecruit.fetch(make_client(lambda request: httpx.Response(200, text=EDIGMA_PAGE)),
                             {"name": "Edigma", "url": "https://careers.edigma.com/jobs/Careers/"})
    [job] = jobs  # the unpublished one is left out
    assert job.title == "AI Software Developer – Integrações & Automação Inteligente"
    assert (job.location, job.posted_at, job.contract, job.experience) == ("Braga", "2026-10-22", "Full time", "1-3 years")
    assert job.url == "https://careers.edigma.com/jobs/Careers/42419000004875003"
    assert job.description == "Sobre a função\nProcuramos um(a) developer para soluções de AI."


def test_zohorecruit_page_without_jobs(make_client):
    with pytest.raises(RuntimeError, match="Zoho Recruit"):
        zohorecruit.fetch(make_client(lambda request: httpx.Response(200, text="<html></html>")),
                          {"name": "Edigma", "url": "https://careers.edigma.com/jobs/Careers"})


# --- Eurotux -----------------------------------------------------------------

def _item(slug, text):
    return (f'<li class="elementor-icon-list-item"><a href="https://eurotux.com/careers/{slug}/" target="_blank">'
            f'<span class="elementor-icon-list-icon"><i class="fas fa-user"></i></span>'
            f'<span class="elementor-icon-list-text">{text}</span></a></li>')


EUROTUX_LIST = ("<ul>" + _item("windows-systems-administrator-ref-001-2026-job-offer", "Windows Systems Administrator (Ref 001-2026)")
                + _item("devops-aws-braga-ref0032026-joboffer", "DevOps AWS - Braga (Ref 003-2026)")
                + _item("networking-administrator-braga-ref-010-2026-job-offer", "Networking Administrator – Braga (Ref 010-2026)")
                + _item("systems-administrator-enduser-ref-012-2026-job-offer", "Systems Administrator - EndUser (Ref 012-2026)")
                + _item("politica-de-privacidade-2022", "Política de Privacidade") + "</ul>")
EUROTUX_DETAIL = ('<script type="application/ld+json">{"datePublished":"2020-06-26T16:45:08+00:00",'
                  '"dateModified":"2026-08-05T10:29:15+00:00"}</script><nav>JOB OPPORTUNITIES INTERNSHIPS</nav>'
                  '<h1>DevOps AWS &#8211; Braga (Ref 003-2026) &#8211; Job Offer</h1>'
                  '<p>Its main responsibilities are:</p><ul><li>Infrastructure management with Ansible and Terraform.</li></ul>'
                  '<p>Submit your application</p><p>SUBSCRIBE TO OUR NEWSLETTER</p>')


def test_eurotux_list_and_detail(make_client):
    seen = []

    def handler(request):
        seen.append(request.url.path)
        return httpx.Response(200, text=EUROTUX_LIST if request.url.path.endswith("job-opportunities/") else EUROTUX_DETAIL)

    jobs = eurotux.fetch(make_client(handler), {}, prefilter=lambda job: "DevOps" in job.title)
    assert [(j.title, j.location) for j in jobs] == [
        ("Windows Systems Administrator", ""), ("DevOps AWS", "Braga"),
        ("Networking Administrator", "Braga"),  # an en dash works too
        ("Systems Administrator - EndUser", "")]  # "EndUser" is part of the name, not a place
    devops = jobs[1]
    assert devops.uid == "eurotux:devops-aws-braga-ref0032026-joboffer" and devops.company == "Eurotux"
    assert devops.posted_at == "2026-08-05"  # dateModified: the 2020 page is reused for each new job
    assert "Ansible and Terraform" in devops.description and "NEWSLETTER" not in devops.description
    assert seen == ["/careers/job-opportunities/", "/careers/devops-aws-braga-ref0032026-joboffer/"]  # no page for the other


# --- Teamtailor --------------------------------------------------------------

TEAMTAILOR_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:tt="https://teamtailor.com/locations"><channel><title>Nutrium</title>
<item>
  <title>Android Developer</title>
  <description><![CDATA[<p>Welcome to Nutrium.</p><ul><li>Kotlin and Jetpack Compose</li></ul>]]></description>
  <pubDate>Wed, 14 Oct 2026 10:12:31 +0100</pubDate>
  <link>https://careers.nutrium.com/jobs/8543944-android-developer</link>
  <guid isPermaLink="false">77e7f98c-61cc-4783-9efc-842a9e9ab6de</guid>
  <remoteStatus>fully</remoteStatus>
  <tt:department>Engineering</tt:department>
  <tt:locations><tt:location><tt:name>Portugal</tt:name><tt:city>Braga</tt:city><tt:country>Portugal</tt:country></tt:location></tt:locations>
</item>
<item>
  <title>Platform Security Engineer</title>
  <description><![CDATA[<p>Cloud security at Coverflex.</p>]]></description>
  <pubDate>Wed, 30 Sep 2026 09:00:00 +0100</pubDate>
  <link>https://coverflex.teamtailor.com/jobs/7000001-platform-security-engineer</link>
  <remoteStatus>hybrid</remoteStatus>
  <tt:locations></tt:locations>
</item>
</channel></rss>"""


def test_teamtailor_feed(make_client):
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, text=TEAMTAILOR_RSS)

    android, security = teamtailor.fetch(make_client(handler), {"company": "nutrium", "name": "Nutrium"})
    assert seen == ["https://nutrium.teamtailor.com/jobs.rss"]  # one request, descriptions included
    assert (android.uid, android.company, android.location) == ("teamtailor:nutrium:8543944", "Nutrium", "Braga")
    assert (android.posted_at, android.work_model) == ("2026-10-14", "remote")
    assert android.url == "https://careers.nutrium.com/jobs/8543944-android-developer"
    assert android.description == "Welcome to Nutrium.\nKotlin and Jetpack Compose"
    assert (security.location, security.work_model) == ("", "hybrid")  # no city: the filters look in the text


def test_teamtailor_on_its_own_domain(make_client):
    seen = []
    teamtailor.fetch(make_client(lambda r: seen.append(str(r.url)) or httpx.Response(200, text="<rss></rss>")),
                     {"company": "criticaltechworks", "url": "https://join.criticaltechworks.com/"})
    assert seen == ["https://join.criticaltechworks.com/jobs.rss"]


# --- Balanças Marques --------------------------------------------------------

def _card(slug, title):
    return (f'<button type="button" class="job-share" data-url="/vagas/{slug}/" data-title="{title}" '
            f'aria-label="Partilhar oferta"><img src="/share.svg"></button>'
            f'<a href="/vagas/{slug}/" class="card red job-cover-card"><div class="job-card-media"></div></a>')


BM_LIST = (_card("agentic-development-engineer", "Agentic Development Engineer (AI-Native Engineering)")
           + _card("serralheiro", "Serralheiros/Soldadores") + _card("candidaturaespontanea", "Candidatura Espontânea"))


def _meta(label, value):
    return (f'<div class="job-meta-item"><span class="job-meta-label">{label}</span>\n'
            f'    <span class="job-meta-value">{value}                            </span></div>')


BM_DETAIL = ('<div class="search-box"><form action="/pesquisa" method="get"></form></div>'
             '<h1>Agentic Development Engineer (AI-Native Engineering)  </h1>'
             '<button type="button" class="job-share1"><span>Partilhar</span></button><div class="job-meta">'
             + _meta("Empresa", "SDILAB") + _meta("Data", "2026-09-28") + _meta("Refer&ecirc;ncia", "SDI-AINE-2026")
             + _meta("Regime", "Full time | Presencial") + _meta("Pa&iacute;s", "Portugal") + _meta("Cidade", "Braga")
             + '</div><div class="value-content"><h2>Quem somos</h2><p>Somos a software house que desenvolve o ETPOS.</p></div>'
             '<button type="button" class="job-share1 job-social-share"><span>Partilhar</span></button>'
             '<div id="contacts"><h6><b>FORMULÁRIO DE CANDIDATURA</b></h6><form class="ajax-submit"></form></div>')


def test_balancasmarques_list_and_detail(make_client):
    seen = []

    def handler(request):
        seen.append(request.url.path)
        return httpx.Response(200, text=BM_LIST if request.url.path == "/recrutamento" else BM_DETAIL)

    jobs = balancasmarques.fetch(make_client(handler), {}, prefilter=lambda job: "Engineer" in job.title)
    assert [j.title for j in jobs] == ["Agentic Development Engineer (AI-Native Engineering)", "Serralheiros/Soldadores"]
    assert seen == ["/recrutamento", "/vagas/agentic-development-engineer/"]  # no page for the welders
    job = jobs[0]
    assert (job.uid, job.company, job.location) == ("balancasmarques:agentic-development-engineer", "SDILAB", "Braga")
    assert (job.posted_at, job.contract, job.work_model) == ("2026-09-28", "Full time", "on-site")
    assert job.url == "https://www.balancasmarques.com/vagas/agentic-development-engineer/"
    assert job.description == "Quem somos\nSomos a software house que desenvolve o ETPOS."
    assert jobs[1].company == "Balanças Marques"  # list data only, until the detail says otherwise
