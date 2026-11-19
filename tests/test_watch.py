"""Watched pages: the careers pages of companies without a job platform, and what changed on them."""

import shutil
from pathlib import Path
from types import SimpleNamespace

import httpx
from fastapi.testclient import TestClient

from jobradar import link, watch
from jobradar.app import create_app
from jobradar.db import Database
from jobradar.refresh import run_refresh

PAGE = """<html><head><style>.x{}</style><script>var a = 1;</script></head><body>
<header>Logo</header><nav><a>Início</a><a>Sobre</a></nav>
<h2>Vagas abertas</h2><ul><li>Junior Backend Developer</li><li>Estágio em Data</li></ul>
<p>Atualizado a 12/11/2026</p><p>42</p><p>Vagas abertas</p><footer>© 2026 Empresa</footer></body></html>"""


def test_page_lines_keep_the_visible_text_without_menus_or_dates():
    # "42", the repeated line, the menus, header, footer, script and style are gone;
    # a line with words and a date stays
    assert watch.page_lines(PAGE) == ["Vagas abertas", "Junior Backend Developer", "Estágio em Data",
                                      "Atualizado a 12/11/2026"]


def test_added_lines_are_the_new_ones_in_page_order():
    assert watch.added_lines(["A", "B"], ["A", "C", "B", "D"]) == ["C", "D"]
    assert watch.added_lines(["A", "B"], ["B", "A"]) == []


def test_relevance_needs_one_of_the_persons_words():
    words = watch.watch_words({"search": {"title_keywords": ["backend", "software"], "levels": ["junior"]}})
    assert "backend" in words and "junior" in words
    assert watch.is_relevant(["Junior Backend Developer"], words)
    assert watch.is_relevant(["Estágio em Software"], words)  # without accents or capitals
    assert not watch.is_relevant(["Testemunho da Ana, 12/11/2026", "Atualizado a 13/11/2026"], words)


# --- reading the pages at each search ------------------------------------------------------------------------

TEXT = "".join(f"<p>Projeto {i}: soluções para clientes da indústria e do retalho.</p>" for i in range(6))
# (distinct lines: page_lines drops repeated ones, and a page needs 200 characters of text)


def site(pages, robots=None, fail=()):
    """robots: host -> robots.txt text (none: 404, everything allowed)."""
    def handler(request):
        host = request.headers["Host"]
        if host in fail:
            raise httpx.ConnectError("down")
        if request.url.path == "/robots.txt":
            text = (robots or {}).get(host)
            return httpx.Response(200, text=text) if text else httpx.Response(404)
        return httpx.Response(200, text=pages[(host, request.url.path)], headers={"content-type": "text/html"})
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_first_read_keeps_the_text_then_a_relevant_line_is_a_change(tmp_path, monkeypatch, cfg):
    monkeypatch.setattr(link, "_resolve", lambda host: "93.184.216.34")
    cfg["search"]["title_keywords"] = ["backend"]
    db = Database(tmp_path / "t.db")
    db.add_watched("F3M", "https://recrutamento.f3m.pt/")
    pages = {("recrutamento.f3m.pt", "/"): TEXT + "<li>Backend Developer Sénior em Braga</li>"}
    # the first read never warns, even with the person's words on the page
    assert watch.check_pages(db, cfg, site(pages), "2026-11-18T09:00", pause=0) == []
    assert db.watched_pages()[0]["changed_at"] is None
    pages[("recrutamento.f3m.pt", "/")] += "<li>Junior Backend Developer</li><p>Atualizado a 18/11</p>"
    changed = watch.check_pages(db, cfg, site(pages), "2026-11-18T21:00", pause=0)
    assert [p["name"] for p in changed] == ["F3M"]
    [page] = db.watched_pages()
    assert page["added"] == ["Junior Backend Developer", "Atualizado a 18/11"] and page["relevant"]
    assert page["changed_at"] == "2026-11-18T21:00"
    assert watch.check_pages(db, cfg, site(pages), "2026-11-19T09:00", pause=0) == []  # nothing new
    [page] = db.watched_pages()
    assert page["changed_at"] == "2026-11-18T21:00" and page["checked_at"] == "2026-11-19T09:00"


def test_a_change_without_the_persons_words_is_recorded_without_a_warning(tmp_path, monkeypatch, cfg):
    monkeypatch.setattr(link, "_resolve", lambda host: "93.184.216.34")
    cfg["search"]["title_keywords"] = ["backend"]
    db = Database(tmp_path / "t.db")
    db.add_watched("Growin", "https://www.growin.com/careers")
    pages = {("www.growin.com", "/careers"): TEXT}
    watch.check_pages(db, cfg, site(pages), "2026-11-18T09:00", pause=0)
    pages[("www.growin.com", "/careers")] += "<p>Testemunho da Ana: adoro a equipa, 12/11/2026</p>"
    assert watch.check_pages(db, cfg, site(pages), "2026-11-18T21:00", pause=0) == []
    [page] = db.watched_pages()
    assert page["added"] == ["Testemunho da Ana: adoro a equipa, 12/11/2026"] and not page["relevant"]
    assert page["changed_at"] == "2026-11-18T21:00"


def test_robots_js_pages_and_a_site_down_are_errors_of_that_page_only(tmp_path, monkeypatch, cfg):
    monkeypatch.setattr(link, "_resolve", lambda host: "93.184.216.34")
    db = Database(tmp_path / "t.db")
    for name, url in [("Proibida", "https://a.pt/careers"), ("JS", "https://b.pt/jobs"),
                      ("Em baixo", "https://c.pt/x"), ("Boa", "https://d.pt/carreiras")]:
        db.add_watched(name, url)
    pages = {("a.pt", "/careers"): TEXT, ("b.pt", "/jobs"): "<div id='app'></div>", ("d.pt", "/carreiras"): TEXT}
    client = site(pages, robots={"a.pt": "User-agent: *\nDisallow: /careers\n"}, fail={"c.pt"})
    watch.check_pages(db, cfg, client, "2026-11-18T09:00", pause=0)
    by = {p["name"]: p for p in db.watched_pages()}
    assert "robots.txt" in by["Proibida"]["error"] and not by["Proibida"]["lines"]
    assert "JavaScript" in by["JS"]["error"]
    assert by["Em baixo"]["error"] and not by["Boa"]["error"] and by["Boa"]["lines"]
    assert all(p["checked_at"] == "2026-11-18T09:00" for p in by.values())


def test_an_error_keeps_the_last_text_and_the_next_good_read_clears_it(tmp_path, monkeypatch, cfg):
    monkeypatch.setattr(link, "_resolve", lambda host: "93.184.216.34")
    db = Database(tmp_path / "t.db")
    db.add_watched("Boa", "https://d.pt/carreiras")
    pages = {("d.pt", "/carreiras"): TEXT}
    watch.check_pages(db, cfg, site(pages), "2026-11-18T09:00", pause=0)
    watch.check_pages(db, cfg, site(pages, fail={"d.pt"}), "2026-11-18T21:00", pause=0)
    [page] = db.watched_pages()
    assert page["error"] and page["lines"]  # a site down for a while isn't a change when it comes back
    assert watch.check_pages(db, cfg, site(pages), "2026-11-19T09:00", pause=0) == []
    [page] = db.watched_pages()
    assert page["error"] == "" and page["changed_at"] is None


def test_refresh_checks_the_watched_pages(tmp_path, monkeypatch, cfg):
    calls = []
    monkeypatch.setattr(watch, "check_pages", lambda db, cfg, client, now, pause=1.0: calls.append(now) or [])
    run_refresh(cfg, Database(tmp_path / "t.db"), client=SimpleNamespace(),
                fetchers={"lever": lambda c, e, prefilter=None: []})
    assert len(calls) == 1


def test_a_broken_page_check_never_stops_the_search(tmp_path, monkeypatch, cfg):
    def boom(*args, **kwargs):
        raise ValueError("bug")
    monkeypatch.setattr(watch, "check_pages", boom)
    summaries = run_refresh(cfg, Database(tmp_path / "t.db"), client=SimpleNamespace(),
                            fetchers={"lever": lambda c, e, prefilter=None: []})
    assert summaries  # the sources' results still come back


# --- the API -------------------------------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]


def app_client(tmp_path):
    shutil.copy(ROOT / "config.example.yaml", tmp_path / "config.yaml")
    return TestClient(create_app(config_path=tmp_path / "config.yaml", db_path=tmp_path / "t.db"))


def test_pages_api_adds_lists_and_removes(tmp_path, monkeypatch):
    monkeypatch.setattr(link, "_resolve", lambda host: "93.184.216.34")
    tc = app_client(tmp_path)
    added = tc.post("/api/pages", json={"name": "F3M", "url": "https://recrutamento.f3m.pt/"})
    assert added.status_code == 200 and added.json()["name"] == "F3M"
    [page] = tc.get("/api/pages").json()
    assert page["name"] == "F3M" and "lines" not in page and page["hits"] == []
    assert tc.delete("/api/pages", params={"url": "https://recrutamento.f3m.pt/"}).status_code == 200
    assert tc.get("/api/pages").json() == []
    assert tc.delete("/api/pages", params={"url": "https://recrutamento.f3m.pt/"}).status_code == 404


def test_pages_api_refuses_local_and_non_web_addresses(tmp_path, monkeypatch):
    monkeypatch.setattr(link, "_resolve", lambda host: None if host in ("localhost", "192.168.1.1") else "93.184.216.34")
    tc = app_client(tmp_path)
    for bad in ("http://localhost/x", "http://192.168.1.1/", "file:///etc/passwd", "ftp://x.pt/", "x.pt/careers",
                "https://www.linkedin.com/company/x/jobs"):
        assert tc.post("/api/pages", json={"name": "X", "url": bad}).status_code == 400, bad
    assert tc.post("/api/pages", json={"name": "", "url": "https://x.pt/"}).status_code == 422
    assert tc.get("/api/pages").json() == []


def test_pages_api_marks_the_new_lines_with_the_persons_words(tmp_path, monkeypatch):
    monkeypatch.setattr(link, "_resolve", lambda host: "93.184.216.34")
    tc = app_client(tmp_path)
    tc.post("/api/pages", json={"name": "F3M", "url": "https://recrutamento.f3m.pt/"})
    db = Database(tmp_path / "t.db")
    db.save_page("https://recrutamento.f3m.pt/", checked_at="2026-11-18T21:00", changed_at="2026-11-18T21:00",
                 lines=["a"], added=["Junior Backend Developer", "Atualizado a 18/11"], relevant=True)
    [page] = tc.get("/api/pages").json()
    assert page["hits"] == ["Junior Backend Developer"] and page["relevant"]
