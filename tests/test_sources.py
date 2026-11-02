import json
from datetime import date

import httpx
import pytest

from jobradar.sources import (SourceSkipped, bamboohr, itjobs, landingjobs, lever, netempregos, randstad,
                              smartrecruiters, successfactors, sysmatch, workday)


# --- SmartRecruiters -------------------------------------------------------

def sr_posting(pid, name, city="Braga", level="Entry Level"):
    return {
        "id": pid,
        "name": name,
        "company": {"identifier": "BoschGroup", "name": "Bosch Group"},
        "releasedDate": "2026-10-20T10:00:00.000Z",
        "location": {"city": city, "region": "Braga", "country": "pt",
                     "fullLocation": f"{city}, , Portugal"},
        "typeOfEmployment": {"label": "Full-time"},
        "experienceLevel": {"label": level},
    }


def test_smartrecruiters_paginates_and_only_loads_details_for_kept(make_client):
    calls = []

    def handler(request: httpx.Request):
        calls.append(str(request.url))
        path = request.url.path
        if path.endswith("/postings"):
            offset = int(request.url.params["offset"])
            assert request.url.params["country"] == "pt"
            if offset == 0:
                # server caps limit at 100 and echoes it back
                content = [sr_posting(str(i), f"Job {i}") for i in range(100)]
                return httpx.Response(200, json={"offset": 0, "limit": 100,
                                                 "totalFound": 101, "content": content})
            return httpx.Response(200, json={"offset": 100, "limit": 100, "totalFound": 101,
                                             "content": [sr_posting("x", "Junior AI Engineer")]})
        return httpx.Response(200, json={
            "postingUrl": "https://jobs.smartrecruiters.com/BoschGroup/x-junior-ai",
            "jobAd": {"sections": {
                "jobDescription": {"text": "<p>Build <b>LLM</b> agents in Python</p>"},
                "qualifications": {"text": "<ul><li>MSc</li></ul>"}}},
        })

    jobs = smartrecruiters.fetch(
        make_client(handler), {"company": "BoschGroup", "country": "pt"},
        prefilter=lambda j: j.title.startswith("Junior"),
    )
    assert len(jobs) == 101
    detail_calls = [c for c in calls if "/postings/" in c]
    assert detail_calls == ["https://api.smartrecruiters.com/v1/companies/BoschGroup/postings/x"]
    junior = jobs[-1]
    assert junior.uid == "smartrecruiters:BoschGroup:x"
    assert junior.company == "Bosch Group"
    assert junior.location == "Braga, Portugal"
    assert junior.posted_at == "2026-10-20"
    assert "LLM agents in Python" in junior.description
    assert junior.url.endswith("x-junior-ai")


# --- Lever -----------------------------------------------------------------

LEVER_POSTING = {
    "id": "24c412e5",
    "text": "Junior Software Engineer - Back End",
    "categories": {"location": "Porto", "team": "Technology", "commitment": "Full-time"},
    "hostedUrl": "https://jobs.lever.co/farfetch/24c412e5",
    "createdAt": 1793000000000,
    "descriptionPlain": "We use Python and REST APIs.",
    "lists": [{"text": "Requirements", "content": "<li>Unit tests</li>"}],
    "workplaceType": "hybrid",
}


def test_lever_falls_back_to_eu_host(make_client):
    def handler(request):
        if request.url.host == "api.lever.co":
            return httpx.Response(404)
        return httpx.Response(200, json=[LEVER_POSTING])

    jobs = lever.fetch(make_client(handler), {"site": "farfetch", "company": "FARFETCH"})
    assert len(jobs) == 1
    job = jobs[0]
    assert job.company == "FARFETCH"
    assert job.location == "Porto"
    assert job.work_model == "hybrid"
    assert "Unit tests" in job.description
    assert job.posted_at and job.posted_at.startswith("2026-")


def test_lever_empty_global_board_tries_eu(make_client):
    hosts = []

    def handler(request):
        hosts.append(request.url.host)
        return httpx.Response(200, json=[] if request.url.host == "api.lever.co" else [LEVER_POSTING])

    jobs = lever.fetch(make_client(handler), {"site": "farfetch"})
    assert hosts == ["api.lever.co", "api.eu.lever.co"]
    assert jobs[0].company == "Farfetch"


# --- Workday ---------------------------------------------------------------

def test_workday_parse_board_strips_locale():
    assert workday.parse_board("https://hrhub.wd3.myworkdayjobs.com/en-US/Euronext_Career_Page") == (
        "hrhub.wd3.myworkdayjobs.com", "hrhub", "Euronext_Career_Page")


@pytest.mark.parametrize("text,expected", [
    ("Posted Today", "2026-10-30"),
    ("Posted Yesterday", "2026-10-29"),
    ("Posted 3 Days Ago", "2026-10-27"),
    ("Posted 30+ Days Ago", "2026-09-30"),
    (None, None),
])
def test_workday_posted_on(text, expected):
    assert workday.posted_on_to_date(text, date(2026, 10, 30)) == expected


def test_workday_fetch_with_detail(make_client):
    seen = []

    def handler(request):
        seen.append((request.method, request.url.path))
        if request.method == "POST":
            body = json.loads(request.content)
            assert body["limit"] == 20
            return httpx.Response(200, json={"total": 2, "jobPostings": [
                {"title": "Developer Trainee", "externalPath": "/job/Porto/Developer-Trainee_R29096",
                 "locationsText": "Porto", "postedOn": "Posted 3 Days Ago", "bulletFields": ["R29096"]},
                {"title": "Senior Java Developer", "externalPath": "/job/Porto/Senior_R1",
                 "locationsText": "Porto", "postedOn": "Posted Today", "bulletFields": ["R1"]},
            ]})
        return httpx.Response(200, json={"jobPostingInfo": {
            "jobDescription": "<p>Python, JavaScript, Docker</p>", "location": "Porto",
            "timeType": "Full time"}})

    jobs = workday.fetch(
        make_client(handler),
        {"name": "Euronext", "url": "https://hrhub.wd3.myworkdayjobs.com/Euronext_Career_Page"},
        prefilter=lambda j: "Senior" not in j.title,
        today=date(2026, 10, 30),
    )
    assert [j.uid for j in jobs] == ["workday:Euronext:R29096", "workday:Euronext:R1"]
    trainee = jobs[0]
    assert trainee.url == "https://hrhub.wd3.myworkdayjobs.com/Euronext_Career_Page/job/Porto/Developer-Trainee_R29096"
    assert trainee.description == "Python, JavaScript, Docker"
    assert trainee.posted_at == "2026-10-27"
    assert ("GET", "/wday/cxs/hrhub/Euronext_Career_Page/job/Porto/Developer-Trainee_R29096") in seen
    assert not any("Senior_R1" in path for method, path in seen if method == "GET")


# --- ITJobs ----------------------------------------------------------------

def itjobs_item(jid, title, location="Braga", contract=("3", "Estágio profissional")):
    return {
        "id": jid, "title": title, "slug": "web-developer-estagio",
        "company": {"name": "GoFact", "logo": "https://static.itjobs.pt/images/companies/1/logo.png"},
        "body": "<p>PHP, MySQL, JavaScript</p>",
        "locations": [{"id": "4", "name": location}],
        "contracts": [{"id": contract[0], "name": contract[1]}],
        "types": [{"id": "1", "name": "Full-time"}],
        "workModel": 2, "publishedAt": "2026-10-28 09:00:00",
    }


def test_itjobs_lists_every_job_in_a_location(make_client):
    calls = []

    def handler(request):
        calls.append((request.url.path, dict(request.url.params)))
        return httpx.Response(200, json={"total": 1, "results": [itjobs_item(7, "Java Fullstack")]})

    jobs = itjobs.fetch(make_client(handler), {"locations": [4], "professional_internships": False}, api_key="k")
    assert [j.title for j in jobs] == ["Java Fullstack"]
    assert calls[0][0] == "/job/list.json" and calls[0][1]["location"] == "4"


def test_itjobs_contract_names_come_from_the_id():
    # the real API answers "Internship" (3) and "Academic" (5), but the filters look for
    # "estágio profissional" / "estágio académico", as in the docs
    def contract(*pairs):
        item = {**itjobs_item(1, "Dev"), "contracts": [{"id": i, "name": n} for i, n in pairs]}
        return itjobs.to_job(item).contract

    assert contract(("3", "Internship")) == "Estágio profissional, Full-time"
    assert contract(("5", "Academic")) == "Estágio académico, Full-time"
    # open to every contract type, so not an academic-only job
    assert contract(("2", "Permanent"), ("3", "Internship"), ("5", "Academic")) == \
        "Permanent, Estágio profissional, Full-time"


def test_itjobs_remote_job_without_locations():
    job = itjobs.to_job({**itjobs_item(1, "Dev"), "locations": None, "workModel": 1})
    assert job.location == "" and job.work_model == "remote"


def test_itjobs_requires_key(make_client, monkeypatch):
    monkeypatch.delenv("ITJOBS_API_KEY", raising=False)
    with pytest.raises(SourceSkipped):
        itjobs.fetch(make_client(lambda r: httpx.Response(500)), {"queries": ["junior"]})


def test_itjobs_dedupes_across_queries(make_client):
    def handler(request):
        assert request.url.params["api_key"] == "k"
        return httpx.Response(200, json={"total": 1, "results": [itjobs_item(1, "Web Developer")]})

    jobs = itjobs.fetch(make_client(handler), {"queries": ["junior", "estagio"]}, api_key="k")
    assert len(jobs) == 1
    job = jobs[0]
    assert job.url == "https://www.itjobs.pt/oferta/1/web-developer-estagio"
    assert job.contract == "Estágio profissional, Full-time"
    assert job.work_model == "hybrid"
    assert job.location == "Braga"
    assert job.logo == "https://static.itjobs.pt/images/companies/1/logo.png"


def test_itjobs_retries_as_post_when_get_key_is_refused(make_client):
    methods = []

    def handler(request):
        methods.append(request.method)
        if request.method == "GET":
            return httpx.Response(200, json={"error": {"message": "Invalid API Key"}})
        form = dict(httpx.QueryParams(request.content.decode()))
        assert form["api_key"] == "k" and form["q"] == "junior"
        return httpx.Response(200, json={"total": 1, "results": [itjobs_item(1, "Web Developer")]})

    jobs = itjobs.fetch(make_client(handler), {"queries": ["junior"], "professional_internships": False},
                        api_key="k")
    assert methods == ["GET", "POST"]
    assert [j.title for j in jobs] == ["Web Developer"]


def test_itjobs_invalid_key_explains_what_to_check(make_client):
    def handler(request):
        return httpx.Response(200, json={"error": {"message": "Invalid API Key"}})

    with pytest.raises(RuntimeError, match="Confirma a chave no .env"):
        itjobs.fetch(make_client(handler), {"queries": ["junior"]}, api_key="bad")


def test_itjobs_http_error_does_not_leak_key(make_client):
    # httpx's own error message has the full URL, and the GET URL carries the api_key;
    # refresh stores and shows str(exc), so the key would end up in the UI and the db
    with pytest.raises(RuntimeError) as err:
        itjobs.fetch(make_client(lambda r: httpx.Response(429)), {"queries": ["junior"]},
                     api_key="secret123")
    assert "429" in str(err.value)
    assert "secret123" not in str(err.value)


# --- SuccessFactors (Deloitte) ----------------------------------------------

def sf_row(path, title, location, posted):
    # trimmed from jobs.deloitte.pt/search/: each title appears twice (desktop + phone)
    return f'''<tr class="data-row">
<td class="colTitle"><span class="jobTitle hidden-phone"><a href="{path}" class="jobTitle-link">{title}</a></span>
<div class="jobdetail-phone visible-phone"><span class="jobTitle visible-phone">
<a class="jobTitle-link" href="{path}">{title}</a></span></div></td>
<td class="colLocation hidden-phone" headers="hdrLocation">
        <span class="jobLocation">
            {location}
        </span></td>
<td class="colDate hidden-phone" nowrap="nowrap"><span class="jobDate">{posted}
</span></td></tr>'''


def test_successfactors_search_page_and_detail(make_client):
    seen = []
    page = (
        '<span class="paginationLabel" aria-label="Resultados 1 – 2">Resultados <b>1 – 2</b> de <b>2</b></span>'
        + sf_row("/job/Braga-Salesforce-Programmer/1369929355/", "Salesforce Programmer", "Braga, PT", "28/10/2026")
        + sf_row("/job/Lisboa-Senior-SOC-Engineer/1362962455/", "Senior SOC Engineer", "Lisboa, PT", "26/10/2026")
    )

    def handler(request):
        seen.append(request.url.path)
        if request.url.path == "/search/":
            assert request.url.params["locationsearch"] == "Braga"
            return httpx.Response(200, text=page)
        return httpx.Response(200, text='<span class="jobdescription"><p>Salesforce <b>Apex</b> e SQL</p></span>\n</div>')

    jobs = successfactors.fetch(
        make_client(handler), {"name": "Deloitte", "url": "https://jobs.deloitte.pt", "location": "Braga"},
        prefilter=lambda j: j.location.startswith("Braga"),
    )
    assert [j.title for j in jobs] == ["Salesforce Programmer", "Senior SOC Engineer"]
    job = jobs[0]
    assert job.uid == "successfactors:Deloitte:1369929355"
    assert job.url == "https://jobs.deloitte.pt/job/Braga-Salesforce-Programmer/1369929355/"
    assert (job.company, job.location, job.posted_at) == ("Deloitte", "Braga, PT", "2026-10-28")
    assert "Apex e SQL" in job.description
    assert seen == ["/search/", "/job/Braga-Salesforce-Programmer/1369929355/"]


def test_successfactors_sitemap_mode(make_client):
    # EY and Fujitsu load their search with JavaScript from /services/ (disallowed in robots.txt),
    # but publish every job in sitemap.xml, with the city at the start of the URL
    sitemap = """<?xml version="1.0" encoding="UTF-8"?><urlset>
<url><loc>https://www.jobs.global.fujitsu.com/job/Braga-IT-Developer-with-English-03/3406550/</loc><lastmod>2026-10-31</lastmod></url>
<url><loc>https://www.jobs.global.fujitsu.com/job/Braga-SAP-MM-Senior-Consultant-03/4498950/</loc><lastmod>2026-10-31</lastmod></url>
<url><loc>https://www.jobs.global.fujitsu.com/job/Lisbon-Data-Engineer-&amp;-Analyst-Lisb-1349-066/1407451833/</loc></url>
</urlset>"""
    page = ('<span itemprop="title">IT Developer with English\n    </span>'
            '<span itemprop="description" class="x"><p>At Fujitsu, we innovate.</p></span>\n   </div>'
            '<span itemprop="description" class="x"><ul><li>Python and SQL</li></ul></span>\n   </div>')
    seen = []

    def handler(request):
        seen.append(request.url.path)
        return httpx.Response(200, text=sitemap if request.url.path == "/sitemap.xml" else page)

    jobs = successfactors.fetch(
        make_client(handler),
        {"name": "Fujitsu", "url": "https://www.jobs.global.fujitsu.com", "location": "Braga", "sitemap": True},
        prefilter=lambda j: "senior" not in j.title.lower(),
    )
    assert [j.external_id for j in jobs] == ["3406550", "4498950"]  # Braga only
    job = jobs[0]
    assert (job.title, job.location, job.company) == ("IT Developer with English", "Braga", "Fujitsu")
    assert job.url == "https://www.jobs.global.fujitsu.com/job/Braga-IT-Developer-with-English-03/3406550/"
    assert job.posted_at is None  # lastmod is when the sitemap was built, not when the job was posted
    assert "At Fujitsu, we innovate." in job.description and "Python and SQL" in job.description
    assert seen == ["/sitemap.xml", "/job/Braga-IT-Developer-with-English-03/3406550/"]  # no page for the senior one


# --- Sysmatch ---------------------------------------------------------------

@pytest.mark.parametrize("title,expected", [
    ("AWS DevSecOps/ Cloud Platform Engineer – Braga (M/F)", ("Braga", "")),
    (".NET C# Web API (M/F) - Lisboa", ("Lisboa", "")),
    ("Data Engineer - Lisbon (Hybrid) (M/F)", ("Lisbon", "hybrid")),
    ("Java Developer (M/F) - Híbrido", ("", "hybrid")),
    ("Tech Lead .NET+React - Remoto (M/F)", ("", "remote")),
    ("Full-Stack Developer - Lisbon (Full-remote)", ("Lisbon", "remote")),
    ("Senior QA Engineer (M/F) – Leça da Palmeira", ("Leça da Palmeira", "")),
    ("QA – Lisboa - Híbrido (M/F)", ("Lisboa", "hybrid")),
    ("Frontend Developer (m/f) Lisboa", ("Lisboa", "")),
    ("Workplace Services Engineer L2 (USA Resident)- Remote M/F", ("", "remote")),
    ("Gestor/a de Projeto – Híbrido (M/F)", ("", "hybrid")),
    ("QA Tester (m/f)", ("", "")),
])
def test_sysmatch_place_comes_from_the_title(title, expected):
    assert sysmatch.place(title) == expected


def test_sysmatch_list_and_detail(make_client):
    seen = []
    listing = (
        '<div class="list-jobs"><div class="jobItem"><p class="fw-800">AWS DevSecOps/ Cloud Platform Engineer – Braga (M/F)</p>'
        '<button class="button">+</button><a href="/job-opportunities/22211" class="d-none"></a></div>'
        '<div class="jobItem"><p class="fw-800">.NET C# Web API (M/F) - Lisboa</p>'
        '<button class="button">+</button><a href="/job-opportunities/22269" class="d-none"></a></div></div>'
    )
    # the JSON-LD locality is always the head office, so it is ignored
    posting = {"@type": "JobPosting", "datePosted": "2026-10-22", "title": "AWS DevSecOps",
               "description": "Estamos a recrutar:\nAWS, Terraform &amp; Python",
               "hiringOrganization": {"name": "Sysmatch", "logo": "http://sysmatch.com/images/logo/logo.png"},
               "jobLocation": {"address": {"addressLocality": "Lisboa"}}}
    detail = f'<script data-react-helmet="true" type="application/ld+json">{json.dumps(posting)}</script>'

    def handler(request):
        seen.append(request.url.path)
        return httpx.Response(200, text=listing if request.url.path == "/job-opportunities/" else detail)

    jobs = sysmatch.fetch(make_client(handler), {}, prefilter=lambda j: j.location != "Lisboa")
    assert [(j.title, j.location) for j in jobs] == [
        ("AWS DevSecOps/ Cloud Platform Engineer – Braga (M/F)", "Braga"), (".NET C# Web API (M/F) - Lisboa", "Lisboa")]
    job = jobs[0]
    assert job.uid == "sysmatch:22211" and job.company == "Sysmatch"
    assert job.url == "https://www.sysmatch.com/job-opportunities/22211/"
    assert job.posted_at == "2026-10-22" and "AWS, Terraform & Python" in job.description
    assert job.logo == "http://sysmatch.com/images/logo/logo.png"
    assert seen == ["/job-opportunities/", "/job-opportunities/22211/"]


# --- Landing.jobs -------------------------------------------------------------

# trimmed from landing.jobs/feed; the lj: prefix is never declared, so it is not valid XML
LANDING_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xml:lang="en-US" xmlns="http://www.w3.org/2005/Atom">
  <title>Jobs @ Landing.jobs</title>
  <entry>
    <id>https://landing.jobs/at/damia/dynamics-365</id>
    <published>2026-09-22T10:38:15Z</published>
    <link rel="alternate" type="text/html" href="https://landing.jobs/at/damia/dynamics-365?utm_source=rss"/>
    <title>Dynamics 365 &amp; Power Platform</title>
    <content type="html">
      <![CDATA[<img class="logo" src="https://s3.eu-central-1.amazonaws.com/storage.landing.jobs/abc" /><div class="offer-info">At Damia (Permanent), in Multiple Locations<br />Remote policy: Partial remote</div><p>Microsoft Dynamics 365 and <b>Power Platform</b></p>]]>
    </content>
    <author><name>Damia</name></author>
    <lj:city>Lisbon</lj:city>
    <lj:job_type>Permanent</lj:job_type>
    <lj:remote_policy>Partial remote</lj:remote_policy>
    <lj:location><lj:city>Lisbon</lj:city><lj:country>Portugal</lj:country></lj:location>
    <lj:location><lj:city>Braga</lj:city><lj:country>Portugal</lj:country></lj:location>
  </entry>
  <entry>
    <id>https://landing.jobs/at/inscale/net-backend-software-engineer</id>
    <published>2026-10-29T12:25:17Z</published>
    <title>.NET Backend Software Engineer</title>
    <content type="html"><![CDATA[<p>.NET</p>]]></content>
    <author><name>INSCALE</name></author>
    <lj:city>Lisbon</lj:city>
    <lj:job_type>Permanent</lj:job_type>
    <lj:remote_policy>Full remote</lj:remote_policy>
  </entry>
</feed>"""


def test_landingjobs_feed(make_client):
    jobs = landingjobs.fetch(make_client(lambda r: httpx.Response(200, text=LANDING_FEED)), {})
    damia, inscale = jobs
    assert damia.uid == "landingjobs:damia/dynamics-365"
    assert (damia.title, damia.company, damia.location) == ("Dynamics 365 & Power Platform", "Damia", "Lisbon, Braga")
    assert (damia.contract, damia.work_model, damia.posted_at) == ("Permanent", "hybrid", "2026-09-22")
    assert damia.url == "https://landing.jobs/at/damia/dynamics-365"
    assert damia.logo == "https://s3.eu-central-1.amazonaws.com/storage.landing.jobs/abc"
    assert "Dynamics 365 and Power Platform" in damia.description
    # no lj:location blocks: the top-level city is used
    assert (inscale.location, inscale.work_model, inscale.logo) == ("Lisbon", "remote", "")


# --- BambooHR (Uphold) --------------------------------------------------------

def test_bamboohr_list_and_detail(make_client):
    seen = []
    # trimmed from uphold.bamboohr.com/careers/list and /careers/882/detail
    listing = {"meta": {"totalCount": 2}, "result": [
        {"id": "882", "jobOpeningName": " Quality Assurance Analyst ", "departmentLabel": "Engineering",
         "employmentStatusLabel": "Full-Time", "location": {"city": "Braga", "state": None},
         "isRemote": None, "locationType": "2"},
        {"id": "350", "jobOpeningName": "Compliance Officer", "departmentLabel": "Legal",
         "employmentStatusLabel": "Full-Time", "location": {"city": "New York", "state": "New York"},
         "isRemote": None, "locationType": "0"},
    ]}
    detail = {"result": {"jobOpening": {
        "jobOpeningShareUrl": "https://uphold.bamboohr.com/careers/882", "datePosted": "2026-10-29",
        "description": "<p>Test <b>APIs</b> and web apps</p>"}}}

    def handler(request):
        seen.append(request.url.path)
        return httpx.Response(200, json=listing if request.url.path == "/careers/list" else detail)

    jobs = bamboohr.fetch(make_client(handler), {"name": "Uphold", "site": "uphold"},
                          prefilter=lambda j: j.location.startswith("Braga"))
    qa, ny = jobs
    assert qa.uid == "bamboohr:Uphold:882" and qa.company == "Uphold"
    assert (qa.title, qa.location, qa.work_model, qa.contract) == (
        "Quality Assurance Analyst", "Braga", "hybrid", "Full-Time")
    assert qa.url == "https://uphold.bamboohr.com/careers/882" and qa.posted_at == "2026-10-29"
    assert "Test APIs and web apps" in qa.description
    assert (ny.location, ny.work_model) == ("New York, New York", "on-site")
    assert seen == ["/careers/list", "/careers/882/detail"]


# --- Net-Empregos -------------------------------------------------------------

def ne_item(jid, title, company, category, zone):
    # trimmed from net-empregos.com/rss.asp: the description is escaped HTML inside CDATA
    desc = (f"&lt;b&gt;Empresa: &lt;/b&gt;{company}&lt;br&gt;&lt;b&gt;Categoria: &lt;/b&gt;{category}&lt;br&gt;"
            f"&lt;b&gt;Zona: &lt;/b&gt; {zone}&lt;br&gt;&lt;b&gt;Data: &lt;/b&gt;1-11-2026&lt;br&gt;&lt;br&gt;"
            "&lt;b&gt;Descrição: &lt;/b&gt;Procuramos um programador para a nossa equipa. Principa...&lt;br&gt;")
    return (f"<item><title><![CDATA[{title}]]></title><dc:creator><![CDATA[{company}]]></dc:creator>"
            f"<link>https://www.net-empregos.com/{jid}/{title.lower().replace(' ', '-')}/</link>"
            f"<description><![CDATA[{desc}]]></description><pubDate>Sun, 01 Nov 2026 00:20:00 GMT</pubDate></item>")


def test_netempregos_feed_and_detail(make_client):
    seen = []
    feed = ('<?xml version="1.0" encoding="iso-8859-1"?><rss version="2.0"><channel><title>Net-Empregos</title>'
            + ne_item(16198801, "Programador Java", "Softinsa", "Informática ( Programação )", "Braga")
            + ne_item(16198739, "Administrativo", "Escritório", "Direito / Justiça", "Braga")
            + ne_item(16198802, "Programador PHP", "Webly", "Informática ( Programação )", "Porto")
            + "</channel></rss>")
    # the JSON-LD has raw newlines inside strings (invalid strict JSON) and the page is Windows-1252
    page = ('<script type="application/ld+json">{"@type": "JobPosting", "datePosted": "2026-11-1 00:20 UTC",\n'
            '"description": "Procuramos um programador.\n<BR>Requisitos: Java e SQL.", "employmentType": "FULL_TIME",\n'
            '"hiringOrganization": {"name": "Softinsa", "logo": "https://www.net-empregos.com/logos/softinsa.png"}}'
            '</script>').encode("cp1252")

    def handler(request):
        seen.append(request.url.path)
        if request.url.path == "/rss.asp":
            return httpx.Response(200, content=feed.encode("cp1252"))
        return httpx.Response(200, content=page)

    jobs = netempregos.fetch(make_client(handler), {"categories": ["Informática"]},
                             prefilter=lambda j: j.location == "Braga")
    assert [(j.title, j.location) for j in jobs] == [("Programador Java", "Braga"), ("Programador PHP", "Porto")]
    job = jobs[0]
    assert job.uid == "netempregos:16198801" and job.company == "Softinsa"
    assert job.url == "https://www.net-empregos.com/16198801/programador-java/"
    assert (job.posted_at, job.contract) == ("2026-11-01", "Informática ( Programação ), Full-time")
    assert "Requisitos: Java e SQL." in job.description and "..." not in job.description
    assert job.logo == "https://www.net-empregos.com/logos/softinsa.png"
    assert jobs[1].description.startswith("Procuramos um programador")  # snippet from the feed
    assert seen == ["/rss.asp", "/16198801/programador-java/"]


# --- Randstad -----------------------------------------------------------------

def rs_item(jid, title, city, region):
    # trimmed from randstad.pt/empregos/rss/
    return (f"<item><title>{title}</title><link>https://www.randstad.pt/empregos/x_{jid}/</link>"
            f"<description><![CDATA[Procuramos um perfil para integrar a equipa...]]></description>"
            f"<pubDate>Wed, 28 Oct 2026 12:11:27 GMT</pubDate><guid>{jid}</guid><jobId>{jid}</jobId>"
            f"<city>{city}</city><region>{region}</region><industry></industry></item>")


def test_randstad_feed_and_detail(make_client):
    feed = ("<rss><channel>" + rs_item("DTS-2026-185065", "Data Engineer (m/f/x)", "Braga (Híbrido)", "Braga")
            + rs_item("OTS-2026-186135", "Operador de Reposição", "Ericeira", "Lisboa") + "</channel></rss>")
    posting = {"@type": "JobPosting", "datePosted": "2026-10-28T12:11:27+0000", "employmentType": "FULL_TIME",
               "description": "<p>Pipelines de dados.</p>", "responsibilities": "<ul><li>Spark</li></ul>",
               "skills": "<p>Python e SQL</p>", "industry": "tecnologias de informação"}
    page = f'<script type="application/ld+json">{json.dumps(posting)}</script>'
    seen = []

    def handler(request):
        seen.append(request.url.path)
        return httpx.Response(200, text=feed if request.url.path == "/empregos/rss/" else page)

    jobs = randstad.fetch(make_client(handler), {}, prefilter=lambda j: j.location.startswith("Braga"))
    data, shelf = jobs
    assert data.uid == "randstad:DTS-2026-185065" and data.company == "Randstad"
    assert (data.location, data.work_model, data.posted_at) == ("Braga (Híbrido), Braga", "hybrid", "2026-10-28")
    assert data.contract == "Full-time"
    assert "Pipelines de dados." in data.description and "Spark" in data.description and "Python e SQL" in data.description
    assert shelf.description.startswith("Procuramos um perfil")  # snippet from the feed, no page loaded
    assert seen == ["/empregos/rss/", "/empregos/x_DTS-2026-185065/"]


def test_dotenv_with_bom(tmp_path, monkeypatch):
    from jobradar.config import load_dotenv

    monkeypatch.delenv("ITJOBS_API_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_bytes("﻿ITJOBS_API_KEY= abc123 \n# comment\n".encode("utf-8"))
    load_dotenv(env)
    import os
    assert os.environ["ITJOBS_API_KEY"] == "abc123"
