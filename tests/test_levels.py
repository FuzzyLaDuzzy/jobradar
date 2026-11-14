"""Any level and any job title: search.levels and search.roles (👤 Profile → Level and Roles).
Configs without them work exactly as before (the rest of the tests use the example config, which has none)."""

import copy
import shutil
import typing
from datetime import date
from pathlib import Path

import httpx
import pytest
import yaml
from fastapi.testclient import TestClient

from jobradar import app as app_mod
from jobradar import config, levels, message, scoring
from jobradar.app import create_app
from jobradar.db import Database
from jobradar.filters import evaluate, quick_reject
from jobradar.models import Job
from jobradar.scoring import keyword_score
from jobradar.sources import itjobs, with_area

ROOT = Path(__file__).resolve().parents[1]
TODAY = date(2026, 11, 14)


def job(**kw):
    base = dict(source="test", external_id="1", company="Bosch", title="Backend Engineer", location="Braga",
                url="https://example.com", posted_at="2026-11-01", description="Python, SQL, Docker and REST APIs.")
    base.update(kw)
    return Job(**base)


def wants(cfg, levels_=None, roles=None):
    cfg = copy.deepcopy(cfg)
    if levels_ is not None:
        cfg["search"]["levels"] = levels_
    if roles is not None:
        cfg["search"]["roles"] = roles
    return cfg


def kept(j, cfg):
    keep, reason, flags = evaluate(j, cfg["search"], today=TODAY)
    return keep, reason, flags


# --- the default: what JobRadar always did ---------------------------------------------------

def test_without_levels_it_is_internships_and_junior_as_before(cfg):
    assert "levels" not in cfg["search"] and levels.chosen(cfg["search"]) == ["internship", "junior"]
    assert quick_reject(job(title="Senior Backend Engineer"), cfg["search"]) == "título sénior (senior)"
    assert quick_reject(job(title="Mid-Level Java Developer"), cfg["search"]) is None  # never cut before
    _, reasons = keyword_score(job(title="Junior Backend Engineer"), cfg)
    assert "júnior/estágio" in reasons and "nível pretendido" not in reasons
    # an empty exclude list was "any level"
    assert levels.chosen({**cfg["search"], "exclude_title_keywords": []}) == list(levels.LEVELS)


def test_the_default_prompts_are_unchanged(cfg):
    seen = []

    def handler(request):
        seen.append(request.content.decode())
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": '{"score": 60}'}]}}]})

    c = wants(cfg)
    c["scoring"]["llm"]["provider"] = "gemini"
    scoring.llm_score(job(), c, httpx.Client(transport=httpx.MockTransport(handler)))
    assert "What the candidate is looking for" not in seen[0]
    assert "Candidate profile:" in seen[0]
    prompt = message._prompt({"title": "Dev"}, c["profile"], "Escreve.", c["search"])
    assert prompt == message._prompt({"title": "Dev"}, c["profile"], "Escreve.")  # nothing added
    assert "Nível procurado" not in prompt


def test_default_itjobs_searches_the_same_words(cfg, make_client):
    calls = []

    def handler(request):
        calls.append((request.url.path, request.url.params.get("q"), request.url.params.get("contract")))
        return httpx.Response(200, json={"results": []})

    entry = with_area("itjobs", {**cfg["sources"]["itjobs"][0], "locations": []}, cfg["search"])
    itjobs.fetch(make_client(handler), entry, api_key="k")
    assert {q for _, q, _ in calls if q} == {"junior", "trainee", "estagio", "graduate"}
    assert ("/job/list.json", None, "3") in calls  # every professional internship, as before
    # an older config that lists its own words searches each of them once, in its order
    calls.clear()
    entry = with_area("itjobs", {"queries": ["junior", "trainee", "estagio", "graduate"], "locations": []}, cfg["search"])
    itjobs.fetch(make_client(handler), entry, api_key="k")
    assert [q for _, q, _ in calls if q] == ["junior", "trainee", "estagio", "graduate"]


# --- Senior + Backend Engineer ---------------------------------------------------------------

@pytest.fixture
def senior(cfg):
    return wants(cfg, ["senior"], ["Backend Engineer"])


@pytest.mark.parametrize("title", [
    "Senior Backend Engineer", "Sr. Back-end Engineer (Python)", "Senior/Lead Backend Engineer",
    "Backend Engineer", "Senior Data Engineer",
])
def test_senior_titles_are_kept(senior, title):
    assert kept(job(title=title), senior)[0], title


@pytest.mark.parametrize("title,word", [
    ("Junior Backend Engineer", "junior"), ("Backend Engineering Intern", "intern"),
    ("Lead Backend Engineer", "lead"), ("Engineering Manager", "manager"), ("Mid-level Backend Engineer", "mid"),
])
def test_other_levels_are_cut(senior, title, word):
    keep, reason, _ = kept(job(title=title), senior)
    assert not keep and reason == f"outro nível ({word})"


def test_the_level_field_counts_when_the_title_says_nothing(senior):
    keep, reason, _ = kept(job(experience="Entry Level"), senior)  # SmartRecruiters
    assert not keep and reason == "outro nível (entry level)"
    keep, reason, _ = kept(job(title="Técnico de Informática", contract="Estágio profissional"), senior)  # IEFP
    assert not keep and reason.startswith("outro nível (estagio")
    assert kept(job(experience="Mid-Senior Level"), senior)[0]  # it names senior
    assert kept(job(title="Senior Backend Engineer", experience="Entry Level"), senior)[0]  # the title wins


def test_a_title_naming_a_level_wins_over_the_site_field(cfg):
    """Bosch files many jobs under SmartRecruiters' "Mid-Senior Level": the title says which one it is."""
    mid = wants(cfg, ["junior", "mid"])
    keep, reason, _ = kept(job(title="(Senior) Backend Developer", experience="Mid-Senior Level"), mid)
    assert not keep and reason == "outro nível (senior)"
    keep, _, flags = kept(job(title="Software Engineer", experience="Mid-Senior Level"), mid)
    assert keep and "nível pretendido" in keyword_score(job(title="Software Engineer", experience="Mid-Senior Level"),
                                                         mid, flags)[1]
    # and for the score: a junior title doesn't get the level points from a "Mid-Senior" field for a senior
    senior = wants(cfg, ["senior"])
    assert "nível pretendido" not in keyword_score(job(title="Junior Developer", experience="Mid-Senior Level"),
                                                   senior)[1]


def test_senior_scoring_is_sensible(senior):
    def score(**kw):
        keep, _, flags = kept(job(**kw), senior)
        assert keep
        return keyword_score(job(**kw), senior, flags)

    best, reasons = score(title="Senior Backend Engineer", description="Python, SQL, Docker. 6+ years of experience.")
    assert "nível pretendido" in reasons and "função pretendida" in reasons
    no_role, reasons = score(title="Senior Data Engineer", description="Python, SQL, Docker. 6+ years of experience.")
    assert "função pretendida" not in reasons
    no_level, _ = score(title="Backend Engineer", description="Python, SQL, Docker. 6+ years of experience.")
    plain, _ = score(title="Backend Engineer", description="Python, SQL, Docker.")
    assert best > no_role and best > no_level
    assert no_level == plain  # a senior isn't marked down for the years a job asks
    assert best >= 70


def test_senior_itjobs_searches_senior_and_the_role(senior, make_client):
    calls = []

    def handler(request):
        calls.append((request.url.params.get("q"), request.url.params.get("contract")))
        return httpx.Response(200, json={"results": []})

    entry = with_area("itjobs", {**senior["sources"]["itjobs"][0], "locations": []}, senior["search"])
    itjobs.fetch(make_client(handler), entry, api_key="k")
    assert [q for q, _ in calls if q] == ["senior", "Backend Engineer"]
    assert all(contract is None for _, contract in calls)  # no internships to read


def test_the_ai_is_told_the_level_and_roles(senior):
    seen = []

    def handler(request):
        seen.append(request.content.decode("utf-8"))
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": '{"score": 80}'}]}}]})

    c = copy.deepcopy(senior)
    c["scoring"]["llm"]["provider"] = "gemini"
    scoring.llm_score(job(), c, httpx.Client(transport=httpx.MockTransport(handler)))
    assert "Experience level wanted: senior" in seen[0] and "Target roles: Backend Engineer" in seen[0]
    prompt = message._prompt({"title": "Dev"}, c["profile"], "Escreve.", c["search"])
    assert "Nível procurado: sénior\nFunções procuradas: Backend Engineer\n</perfil>" in prompt


# --- other levels and roles ------------------------------------------------------------------

def test_several_levels_and_years(cfg):
    mid = wants(cfg, ["junior", "mid"])
    assert kept(job(title="Mid-level Developer"), mid)[0] and kept(job(title="Junior Developer"), mid)[0]
    assert not kept(job(title="Senior Developer"), mid)[0]
    assert not kept(job(title="Estágio em Desenvolvimento Web"), mid)[0]  # internship wasn't picked
    plain = dict(title="Software Developer", description="Java and SQL")
    base, _ = keyword_score(job(**plain), mid)
    assert keyword_score(job(**plain), mid, {"years_required": 4})[0] == base  # up to 4 is fine for mid
    assert keyword_score(job(**plain), mid, {"years_required": 5})[0] == base - 5
    assert keyword_score(job(**plain), mid, {"years_required": 6})[0] == base - 20
    # internships and junior, chosen on the screen: the same years as always
    junior = wants(cfg, ["internship", "junior"])
    base, _ = keyword_score(job(**plain), junior)
    assert keyword_score(job(**plain), junior, {"years_required": 2})[0] == base - 5
    assert keyword_score(job(**plain), junior, {"years_required": 3})[0] == base - 20


def test_any_level_cuts_no_level(cfg):
    for any_ in (list(levels.LEVELS), []):  # all of them, or none: any level
        c = wants(cfg, any_)
        for title in ("Senior Developer", "Junior Developer", "Tech Lead Developer", "Software Engineering Intern"):
            assert quick_reject(job(title=title), c["search"]) is None, title
        assert "nível pretendido" not in keyword_score(job(title="Senior Developer"), c)[1]
    # words you added that aren't levels still cut
    c = wants(cfg, list(levels.LEVELS))
    c["search"]["exclude_title_keywords"].append("consultant")
    assert quick_reject(job(title="SAP Consultant"), c["search"]) == "título sénior (consultant)"


def test_a_role_is_not_read_as_a_level_and_needs_no_position_word(cfg):
    c = wants(cfg, ["mid"], ["Product Manager", "Tech Lead"])
    assert kept(job(title="Product Manager"), c)[0]  # "manager" is the role here, not the Lead level
    assert kept(job(title="Tech Lead - Payments"), c)[0]
    assert quick_reject(job(title="Senior Product Manager"), c["search"]) == "outro nível (senior)"
    assert quick_reject(job(title="Office Manager"), c["search"]) == "outro nível (manager)"
    assert "função pretendida" in keyword_score(job(title="Product Manager"), c)[1]
    # outside the IT position words, a role still lets the title in
    outside = wants(cfg, None, ["Marketing Specialist"])
    assert quick_reject(job(title="Marketing Specialist"), outside["search"]) is None
    assert quick_reject(job(title="Marketing Assistant"), outside["search"]) == "fora da área"


def test_role_matching():
    assert levels.matched_roles("Senior Back-end Engineer (Python)", ["backend engineer"]) == ["backend engineer"]
    assert levels.matched_roles("Backend Developer", ["Backend Engineer"]) == []
    assert levels.matched_roles("Engineer, Backend", ["Backend Engineer"]) == ["Backend Engineer"]  # any order
    assert levels.without_roles("Senior Engineering Manager", ["Engineering Manager"]).split() == ["senior"]
    assert levels.without_roles("Senior Engineering Manager", []) == "senior engineering manager"


# --- saving it: config.yaml, the 👤 screen, the ✂ tab ---------------------------------------

def test_unknown_levels_are_refused():
    text = "search:\n  locations: [braga]\n  levels: [senior, boss]\nsources:\n  landingjobs: [{}]\n"
    with pytest.raises(config.ConfigError, match="search.levels"):
        config.parse(text)
    assert config.parse(text.replace(", boss", ", Mid"))["search"]["levels"] == ["senior", "Mid"]  # capitals are fine
    assert levels.chosen({"levels": ["senior", "Mid"]}) == ["mid", "senior"]


def test_the_screen_offers_the_same_levels_as_the_backend():
    assert typing.get_args(app_mod.Level) == levels.LEVELS


@pytest.fixture
def config_path(tmp_path, monkeypatch):
    for key in ("GEMINI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    path = tmp_path / "config.yaml"
    shutil.copy(ROOT / "config.example.yaml", path)
    return path


def test_profile_screen_saves_levels_and_roles(config_path):
    tc = TestClient(create_app(config_path=config_path, db_path=config_path.parent / "t.db"))
    before = config_path.read_text(encoding="utf-8")
    form = tc.get("/api/profile").json()["profile"]
    form.update(levels=["senior"], roles=["Backend Engineer", " backend  engineer ", "Data Engineer"])
    data = tc.put("/api/profile", json=form).json()["profile"]
    assert data["levels"] == ["senior"] and data["roles"] == ["Backend Engineer", "Data Engineer"]
    text = config_path.read_text(encoding="utf-8")
    added = [line for line in text.splitlines() if line not in before.splitlines()]
    assert added == ["  roles: [Backend Engineer, Data Engineer]", "  levels: [senior]"]  # nothing else changes
    # a request without them leaves them as they are
    form.pop("levels"), form.pop("roles")
    assert tc.put("/api/profile", json=form).status_code == 200
    assert config_path.read_text(encoding="utf-8") == text
    assert tc.put("/api/profile", json={**form, "levels": ["boss"]}).status_code == 422


def test_cut_tab_offers_to_add_the_level(config_path):
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config.update({("search", "levels"): ["senior"]}, config_path)
    db = Database(config_path.parent / "t.db")
    db.replace_cut("test", [(job(title="Lead Backend Engineer"), "outro nível (lead)")], "2026-11-14T10:00:00+00:00")
    tc = TestClient(create_app(config_path=config_path, db_path=config_path.parent / "t.db"))
    cut = tc.get("/api/cut").json()
    assert cut[0]["kind"] == "outro nível" and cut[0]["word"] == "lead" and cut[0]["level"] == "lead"
    assert cut[0]["reason"] == "outro nível (lead)"
    resp = tc.post("/api/filters", json={"action": "add", "field": "levels", "word": "lead"})
    assert resp.json()["values"] == ["senior", "lead"]
    assert yaml.safe_load(config_path.read_text(encoding="utf-8"))["search"]["levels"] == ["senior", "lead"]
    assert tc.post("/api/filters", json={"action": "add", "field": "levels", "word": "boss"}).status_code == 400
    assert tc.post("/api/filters", json={"action": "remove", "field": "levels", "word": "lead"}).status_code == 400
    assert cfg["search"]["exclude_title_keywords"]  # the example's list is still there, left to the levels
