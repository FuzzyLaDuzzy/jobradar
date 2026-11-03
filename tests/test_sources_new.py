"""Recruitee (Mercedes-Benz.io), Zoho Recruit (Edigma), Eurotux, Teamtailor (Nutrium), Balanças Marques (with SDILAB),
Workable (search by place), Work in Braga and Greenhouse (Sword Health),
from real answers cut down to a few fields."""

import html
import json

import httpx
import pytest

from jobradar.sources import (balancasmarques, eurotux, greenhouse, recruitee, smartrecruiters, teamtailor, with_area, workable,
                              workinbraga, zohorecruit)

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


# --- Workable (search by place) ----------------------------------------------

WORKABLE_PAGE_1 = {"totalSize": 3, "nextPageToken": "tok2", "jobs": [
    {"id": "f8579e19", "title": "Telecom Billing Software Engineer", "employmentType": "Full-time",
     "description": "<p>Join 1GLOBAL.</p>", "requirementsSection": "<ul><li>Java</li></ul>", "benefitsSection": "",
     "url": "https://jobs.workable.com/view/abc/telecom-billing-software-engineer-in-braga-at-1global",
     "locations": ["Braga, Braga, Portugal"], "location": {"city": "Braga", "subregion": "Braga", "countryName": "Portugal"},
     "created": "2026-10-16T09:12:00.000Z", "workplace": "on_site",
     "company": {"title": "1GLOBAL", "image": "https://workablehr.s3.amazonaws.com/uploads/account/logo/1/logo"}},
    {"id": "a1b2c3d4", "title": "LQA Game Tester (Italian) - Freelance Remote", "employmentType": "Other",
     "description": "<p>Side is a global video game services provider.</p>", "url": "https://jobs.workable.com/view/def/lqa",
     "locations": ["TELECOMMUTE", "Braga, Braga, Portugal"], "location": {"city": "Braga", "countryName": "Portugal"},
     "created": "2026-09-18T10:00:00.000Z", "workplace": "remote", "company": {"title": "Side"}}]}
WORKABLE_PAGE_2 = {"totalSize": 3, "jobs": [
    {"id": "e5f6", "title": "UI/UX Designer", "location": {"city": "Maia"}, "created": "2026-10-20T08:00:00.000Z",
     "workplace": "hybrid", "url": "https://jobs.workable.com/view/ghi/ui", "company": {"title": "Critical Manufacturing"}},
    WORKABLE_PAGE_1["jobs"][0]]}  # the next page can repeat a job


def test_workable_searches_the_area_page_by_page(make_client):
    seen = []

    def handler(request):
        seen.append(dict(request.url.params))
        return httpx.Response(200, json=WORKABLE_PAGE_2 if request.url.params.get("pageToken") else WORKABLE_PAGE_1)

    entry = with_area("workable", {}, {"locations_primary": ["braga"], "locations": ["braga", "guimaraes"]})
    jobs = workable.fetch(make_client(handler), entry)
    assert seen == [{"location": "braga"}, {"location": "braga", "pageToken": "tok2"}]
    assert [j.title for j in jobs] == ["Telecom Billing Software Engineer", "LQA Game Tester (Italian) - Freelance Remote",
                                       "UI/UX Designer"]
    billing, tester, designer = jobs
    assert (billing.uid, billing.company, billing.location) == ("workable:f8579e19", "1GLOBAL", "Braga")
    assert (billing.posted_at, billing.contract, billing.work_model) == ("2026-10-16", "Full-time", "on-site")
    assert billing.description == "Join 1GLOBAL.\nJava" and billing.logo.endswith("/logo")
    assert (tester.contract, tester.work_model) == ("", "remote")  # "Other" says nothing
    assert (designer.location, designer.work_model) == ("Maia", "hybrid")  # nearby: the filters decide


# --- Work in Braga -----------------------------------------------------------

def _offer(node, title, company):
    return (f'<div class="job-offer-card"><a href="https://workinbraga.pt/node/{node}">\n'
            f'    <div class="job-offer-regime">Regime Integral</div>\n'
            f'    <div class="job-offer-title">{title}</div>\n'
            f'    <div class="job-offer-company">{company}</div>\n  </a></div>')


WIB_PAGE_0 = (_offer("8880", "Security Researcher", "Checkmarx Portugal ")
              + _offer("8853", "Assistente Comercial Internacional - Backoffice (m ...", "Grupo Navarra")
              + '<a href="?job=&amp;professional_category=All&amp;page=1">Seguinte</a>')
WIB_PAGE_1 = _offer("8875", "Consultor/a de Conformidade e Regulamenta&ccedil;&atilde;o ", "Eurotux Inform&aacute;tica, S.A.")
WIB_DETAIL = ('<article class="node node--type-job-offer"><div class="col-sm-8"><div class="col-sm-12 job-card-header">'
              '<div class="job-offer-header"><h3>Checkmarx Portugal </h3><h1>Security Researcher</h1></div>'
              '<div class="job-regime col-sm-3"><p>Regime Integral</p></div>'
              '<div class="job-posted-date col-sm-3"><p>Colocado em 24/09/2026</p></div></div>'
              '<div class="col-sm-12 job-card-content"><div class="job-role-description"><p><strong>Who are we?</strong></p></div>'
              '<div class="job-required-skills"><h2>Competências necessárias:</h2><ul><li>Application Security</li></ul></div></div>'
              '<div class="col-sm-12 job-card-actions"><a href="/node/add/job_application?id=8880">Candidatar-me</a></div></div>'
              '<div class="col-sm-4 right-side-wrapper"><div class="company-logo"> <img src="/sites/default/files/logo.png?itok=x" ></div>'
              '<div class="company-email"><a href="mailto:recruiter@example.com">Contacto</a></div></div></article>')


def test_workinbraga_list_and_detail(make_client):
    seen = []

    def handler(request):
        seen.append(str(request.url).replace("https://workinbraga.pt", ""))
        if request.url.path == "/job-offers":
            return httpx.Response(200, text=WIB_PAGE_1 if request.url.params["page"] == "1" else WIB_PAGE_0)
        return httpx.Response(200, text=WIB_DETAIL)

    jobs = workinbraga.fetch(make_client(handler), {}, prefilter=lambda job: "Security" in job.title)
    assert seen == ["/job-offers?page=0", "/job-offers?page=1", "/node/8880"]  # no page for the other offers
    researcher, assistant, consultant = jobs
    assert (researcher.uid, researcher.company, researcher.location) == ("workinbraga:8880", "Checkmarx Portugal", "Braga")
    assert (researcher.posted_at, researcher.contract) == ("2026-09-24", "Regime Integral")
    assert researcher.description == "Who are we?\nCompetências necessárias:\nApplication Security"
    assert "recruiter@" not in researcher.description  # the company card is left out
    assert researcher.logo == "https://workinbraga.pt/sites/default/files/logo.png?itok=x"
    assert assistant.title == "Assistente Comercial Internacional - Backoffice (m"  # cut by the list, no "..."
    assert (consultant.title, consultant.company) == ("Consultor/a de Conformidade e Regulamentação", "Eurotux Informática, S.A.")


# --- Greenhouse --------------------------------------------------------------

GREENHOUSE_JOBS = {"meta": {"total": 2}, "jobs": [
    {"id": 4434773009, "title": "Software Engineer", "company_name": "Sword", "location": {"name": "Hybrid - Lisbon"},
     "absolute_url": "https://job-boards.greenhouse.io/swordhealth/jobs/4434773009",
     "first_published": "2026-10-09T05:39:26-04:00", "updated_at": "2026-10-26T08:28:09-04:00",
     "content": "&lt;p&gt;At Sword, we&amp;rsquo;re building AI Care.&lt;/p&gt;&lt;ul&gt;&lt;li&gt;Python&lt;/li&gt;&lt;/ul&gt;"},
    {"id": 4434773010, "title": "Data Analyst", "company_name": "Sword", "location": {"name": "Remote - Portugal"},
     "absolute_url": "https://job-boards.greenhouse.io/swordhealth/jobs/4434773010", "updated_at": "2026-10-20T10:00:00-04:00",
     "content": ""}]}


def test_greenhouse_board(make_client):
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, json=GREENHOUSE_JOBS)

    engineer, analyst = greenhouse.fetch(make_client(handler), {"company": "swordhealth", "name": "Sword Health"})
    assert seen == ["https://boards-api.greenhouse.io/v1/boards/swordhealth/jobs?content=true"]  # one request
    assert (engineer.uid, engineer.company, engineer.location) == ("greenhouse:swordhealth:4434773009", "Sword Health",
                                                                   "Hybrid - Lisbon")
    assert (engineer.posted_at, engineer.work_model) == ("2026-10-09", "hybrid")
    assert engineer.description == "At Sword, we’re building AI Care.\nPython"  # escaped HTML, read as HTML
    assert (analyst.posted_at, analyst.work_model) == ("2026-10-20", "remote")  # no first_published: updated_at


# --- SmartRecruiters search (by place) ----------------------------------------

def _sr_hit(search_id, posting_id, company, name, city):
    return {"id": search_id, "name": name, "releasedDate": "2026-11-03T11:52:54.902Z",
            "company": {"identifier": company, "name": company},
            "location": {"city": city, "region": "Braga", "country": "pt", "remote": False, "hybrid": True},
            "typeOfEmployment": {}, "experienceLevel": {},
            "actions": {"details": f"https://api.smartrecruiters.com/v1/companies/{company}/postings/{posting_id}"}}


SR_SEARCH = {"offset": 0, "limit": 100, "totalFound": 3, "content": [
    _sr_hit("744000159365001", "13693764001", "BoschGroup", "Junior Software Engineer", "Braga"),  # followed already
    _sr_hit("744000159365002", "13693764002", "Inetum", "Junior Java Developer", "Braga"),
    _sr_hit("744000159365003", "13693764003", "Eurofins", "Laboratory Technician", "Braga")]}
SR_DETAIL = {"id": "13693764002", "postingUrl": "https://jobs.smartrecruiters.com/Inetum/744000159365002-junior-java-developer",
             "typeOfEmployment": {"label": "Full-time"}, "experienceLevel": {"label": "Entry Level"},
             "jobAd": {"sections": {"jobDescription": {"text": "<p>Java and Spring.</p>"}}}}


def test_smartrecruiters_search_by_place(make_client):
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, json=SR_SEARCH if "sr-jobs/search" in request.url.path else SR_DETAIL)

    entry = with_area("smartrecruiters_search", {}, {"locations_primary": ["braga"], "locations": ["braga"]},
                      {"smartrecruiters": [{"company": "BoschGroup", "country": "pt"}]})
    jobs = smartrecruiters.search(make_client(handler), entry, prefilter=lambda job: "Java" in job.title)
    assert [j.company for j in jobs] == ["Inetum", "Eurofins"]  # Bosch is left to its own entry
    assert seen == ["https://jobs.smartrecruiters.com/sr-jobs/search?keyword=braga&limit=100",
                    "https://api.smartrecruiters.com/v1/companies/Inetum/postings/13693764002"]  # no detail for the lab
    java = jobs[0]
    assert java.uid == "smartrecruiters_search:13693764002"  # the posting's id, from the detail link
    assert (java.location, java.work_model) == ("Braga, Braga, PT", "hybrid")
    assert (java.contract, java.experience) == ("Full-time", "Entry Level")  # empty in the search, from the detail
    assert java.description == "Java and Spring."
    assert java.url == "https://jobs.smartrecruiters.com/Inetum/744000159365002-junior-java-developer"
