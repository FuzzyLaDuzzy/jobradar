from datetime import date

import pytest

from jobradar.filters import evaluate, quick_reject, years_required
from jobradar.models import Job
from jobradar.scoring import _parse_llm_reply, combine, keyword_score


def job(**kw):
    base = dict(source="test", external_id="1", company="Bosch", title="Junior AI Software Engineer",
                location="Braga, Portugal", url="https://example.com", posted_at="2026-10-20",
                description="Python, REST APIs, LLM integration, Kubernetes and Helm.")
    base.update(kw)
    return Job(**base)


@pytest.mark.parametrize("title,reason", [
    ("Senior Backend Engineer", "título sénior"),
    ("Tech Lead | AI Factory", "título sénior"),
    ("AI/ML Team Leader", "título sénior"),
    ("Estágio Curricular em Informática", "excluída"),
])
def test_titles_rejected(cfg, title, reason):
    assert quick_reject(job(title=title), cfg["search"]).startswith(reason)


def test_extracurricular_is_not_curricular(cfg):
    search = {**cfg["search"], "exclude_keywords": ["curricular"]}
    assert quick_reject(job(title="Estágio Extracurricular em Engenharia Informática"), search) is None
    # but the example config excludes extracurricular internships too
    assert quick_reject(job(title="Extracurricular Internship – DevOps"), cfg["search"]).startswith("excluída")


def test_excluded_company_and_location(cfg):
    search = {**cfg["search"], "exclude_companies": ["accenture"]}
    assert quick_reject(job(company="Accenture Portugal"), search).startswith("empresa")
    assert quick_reject(job(location="Lisboa, Portugal"), cfg["search"]) == "fora da zona"
    assert quick_reject(job(location="Guimarães"), cfg["search"]) is None  # accents optional
    assert quick_reject(job(location="3 Locations"), cfg["search"]) is None  # unknown: keep


def test_only_braga_area_by_default(cfg):
    assert quick_reject(job(location="Porto"), cfg["search"]) == "fora da zona"
    assert quick_reject(job(location="Remote, Portugal"), cfg["search"]) == "fora da zona"
    # ITJobs sends remote jobs with no location at all
    assert quick_reject(job(location="", work_model="remote"), cfg["search"]) == "fora da zona"
    assert quick_reject(job(location="", work_model="on-site"), cfg["search"]) is None  # unknown: keep


@pytest.mark.parametrize("title", [
    "Purchasing Assistant (f/m/div.)", "Diagnostic Technician", "Internal Controls Coordinator",
    "Estágio Profissional em Engenharia Mecânica (Nível 7)",
])
def test_titles_outside_it_dropped(cfg, title):
    assert quick_reject(job(title=title), cfg["search"]) == "fora da área"


@pytest.mark.parametrize("title", [
    "Global Factory Information Systems Engineer", "Salesforce Programmer", "SAP ABAP / FIORI Consultant",
    "Technology Graduate Programme - Braga", "Data Analyst (f/m/div.)", "Quality Engineer (Tester)",
    "Consultor de Tecnologias de Informação", "BTP Build Process Automation Consultant",
    "Quality Assurance Analyst",
])
def test_it_titles_kept(cfg, title):
    assert quick_reject(job(title=title), cfg["search"]) is None


def test_help_desk_dropped(cfg):
    assert quick_reject(job(title="Técnico de Suporte / Help Desk"), cfg["search"]).startswith("excluída")
    assert quick_reject(job(title="IT Service Desk Analyst"), cfg["search"]).startswith("excluída")
    assert quick_reject(job(title="IT Support with German & English"), cfg["search"]).startswith("excluída")
    # "developer" is an IT word, but a business developer is a sales job
    assert quick_reject(job(title="Business developer- mercado francês"), cfg["search"]).startswith("excluída")
    # SAP as an accounting tool is not IT; SAP consulting still is
    assert quick_reject(job(title="Profissional de Contabilidade e SAP - Español (F/M/X) - Braga"),
                        cfg["search"]).startswith("excluída")
    assert quick_reject(job(title="SAP FI/CO Consultant"), cfg["search"]) is None


def test_missing_location_read_from_the_text(cfg):
    search = cfg["search"]
    # ITJobs and Sysmatch often leave the location empty and only name the city in the text
    assert quick_reject(job(location="", description="Projeto no Porto, regime híbrido"), search) == "fora da zona"
    assert quick_reject(job(location="", description="Escritórios em Lisboa e Braga"), search) is None
    assert quick_reject(job(location="", description="Python e SQL"), search) is None  # unknown: keep


@pytest.mark.parametrize("title", [
    "Telecom Billing Software Engineer - Lisbon Based",  # Workable says Braga, the title says Lisbon
    "Portuguese Customer Agent for E-Commerce Platform - Work Remotely from Greece",
    "Portuguese Social Media and AI Content Specialist - Relocate to Greece",
    "Software Engineer (Porto)",
])
def test_title_naming_another_place_wins(cfg, title):
    assert quick_reject(job(title=title, location="Braga"), cfg["search"]) == "fora da zona"


def test_title_naming_a_place_of_the_area_is_kept(cfg):
    search = cfg["search"]
    assert quick_reject(job(title="Software Engineer (Porto or Braga)", location="Braga"), search) is None
    assert quick_reject(job(title="Software Engineer - Work from Home", location="Braga"), search) is None
    # any area: for someone in Lisbon, "Lisbon Based" is home
    lisbon = {**search, "locations": ["lisboa", "lisbon", "oeiras"]}
    assert quick_reject(job(title="Software Engineer - Lisbon Based", location="Lisboa"), lisbon) is None
    assert quick_reject(job(title="Software Engineer - Braga Based", location="Lisboa"), lisbon) == "fora da zona"
    assert quick_reject(job(location="", description="Escritório em Braga"), lisbon) == "fora da zona"


def test_remote_portugal_allowed_when_enabled(cfg):
    search = {**cfg["search"], "allow_remote": True}
    assert quick_reject(job(location="Remote, Portugal"), search) is None
    assert quick_reject(job(location="Remote, Spain"), search) == "fora da zona"


def test_scam_and_old_jobs_dropped(cfg):
    keep, reason, _ = evaluate(job(description="Visa sponsorship and accommodation provided"),
                               cfg["search"], today=date(2026, 10, 30))
    assert not keep and reason.startswith("suspeita de burla")
    keep, reason, _ = evaluate(job(posted_at="2026-06-01"), cfg["search"], today=date(2026, 10, 30))
    assert not keep and reason == "antiga"


def test_academic_internship_contract_dropped(cfg):
    keep, reason, _ = evaluate(job(title="Web Developer", contract="Estágio académico"),
                               cfg["search"], today=date(2026, 10, 30))
    assert not keep and reason.startswith("excluída")


@pytest.mark.parametrize("text,years", [
    ("2+ years of experience in Software Engineering", 2),
    ("Minimum of 5 years of experience in data science", 5),
    ("3-5 years of professional experience", 3),
    ("mínimo de 3 anos de experiência em Java", 3),
    ("Experience: 4+ years with Python", 4),
    ("Bosch has been around for 140 years", None),
    ("Founded 25 years ago", None),
])
def test_years_required(text, years):
    assert years_required(job(description=text)) == years


def test_keyword_score_rewards_fit(cfg):
    good, reasons = keyword_score(job(), cfg)
    assert good >= 60
    assert "júnior/estágio" in reasons and "zona preferida" in reasons

    plain = dict(title="Software Engineer", location="Braga", description="Java and SQL")
    base, _ = keyword_score(job(**plain), cfg)
    asks_years, _ = keyword_score(job(**plain), cfg, {"years_required": 4})
    mid_senior, _ = keyword_score(job(**plain, experience="Mid-Senior Level"), cfg)
    assert base < good
    assert asks_years == base - 20
    assert mid_senior == base - 10


def test_c_sharp_is_not_c(cfg):
    _, reasons = keyword_score(job(title="Developer", description="Experience with C# and .NET"), cfg)
    assert "c" not in reasons[-1].split(", ")
    _, reasons = keyword_score(job(title="Developer", description="Good C programming skills"), cfg)
    assert "c" in reasons[-1].split(", ")


def test_llm_reply_parsing_and_combine():
    assert _parse_llm_reply('Sure! {"score": 81, "reason": "Encaixa bem"}') == (81, "Encaixa bem")
    assert _parse_llm_reply("no json here") is None
    assert _parse_llm_reply('{"score": 150}') == (100, "")
    assert combine(50, None) == 50
    assert combine(50, 100) == 80
