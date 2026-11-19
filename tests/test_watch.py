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
<header><nav><a>Início</a><a>Sobre</a></nav></header>
<h2>Vagas abertas</h2><ul><li>Junior Backend Developer</li><li>Estágio em Data</li></ul>
<p>Atualizado a 12/11/2026</p><p>42</p><p>Vagas abertas</p><footer><nav><a>Contactos</a></nav></footer></body></html>"""


def test_page_lines_keep_the_visible_text_without_menus_or_dates():
    # "42", the repeated line, the menus, script and style are gone;
    # a line with words and a date stays
    assert watch.page_lines(PAGE) == ["Vagas abertas", "Junior Backend Developer", "Estágio em Data",
                                      "Atualizado a 12/11/2026"]


def test_added_lines_are_the_new_ones_in_page_order():
    assert watch.added_lines(["A", "B"], ["A", "C", "B", "D"]) == ["C", "D"]
    assert watch.added_lines(["A", "B"], ["B", "A"]) == []


def test_a_new_date_or_count_is_not_a_new_line():
    # "Data de atualização: 19/11/2026" would change every day, and "data" is one of the person's words
    assert watch.added_lines(["Data de atualização: 18/11/2026", "12 vagas abertas"],
                             ["Data de atualização: 19/11/2026", "13 vagas abertas", "Junior Developer"]) == ["Junior Developer"]


def test_only_a_line_like_a_job_title_counts():
    # the area words are made for job titles: "ti", "data" or "tecnologia" in a sentence is no job
    words = ["ti", "tecnologia", "developer", "data"]
    assert watch.is_relevant(["Junior Developer - Braga"], words)
    assert watch.is_relevant(["Data Engineer (m/f)"], words)
    assert not watch.is_relevant(["Vem viver a tecnologia connosco e cresce com a nossa equipa todos os dias, em Braga."], words)
    assert not watch.is_relevant(["Licenciatura em TI ou áreas similares;"], words)
    assert not watch.is_relevant(["O nosso blog: tudo sobre tecnologia, inovação, pessoas, eventos e a vida na empresa"], words)


def test_a_job_title_inside_an_article_header_stays():
    # WordPress and similar: each job is an <article> with its title in a <header>
    page = ("<article><header class='entry-header'><h2>Junior Backend Developer</h2></header>"
            "<p>Junta-te à equipa de produto em Braga.</p></article>")
    assert "Junior Backend Developer" in watch.page_lines(page)


def test_lines_the_search_excludes_never_matter(cfg):
    search = cfg["search"]  # Braga's zone, senior/lead excluded, help desk excluded
    words = watch.watch_words(cfg)
    assert watch.is_relevant(["Junior Backend Developer"], words, search)
    assert watch.is_relevant(["Estágio Profissional 2027"], words, search)  # a level word alone is enough
    assert not watch.is_relevant(["Senior Backend Developer"], words, search)
    assert not watch.is_relevant(["Tech Lead - Java"], words, search)
    assert not watch.is_relevant(["Backend Developer - Lisboa"], words, search)
    assert not watch.is_relevant(["Help Desk Technician (IT)"], words, search)


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


def test_an_uninteresting_change_never_hides_one_that_matters(tmp_path, monkeypatch, cfg):
    monkeypatch.setattr(link, "_resolve", lambda host: "93.184.216.34")
    db = Database(tmp_path / "t.db")
    db.add_watched("F3M", "https://recrutamento.f3m.pt/")
    pages = {("recrutamento.f3m.pt", "/"): TEXT}
    watch.check_pages(db, cfg, site(pages), "2026-11-19T09:00", pause=0)
    pages[("recrutamento.f3m.pt", "/")] += "<li>Junior Backend Developer</li>"
    watch.check_pages(db, cfg, site(pages), "2026-11-19T21:00", pause=0)
    pages[("recrutamento.f3m.pt", "/")] += "<p>Testemunho da Ana: adoro a equipa</p>"
    assert watch.check_pages(db, cfg, site(pages), "2026-11-20T09:00", pause=0) == []
    [page] = db.watched_pages()
    assert page["relevant"] and page["added"] == ["Junior Backend Developer"]
    assert page["changed_at"] == "2026-11-19T21:00" and page["checked_at"] == "2026-11-20T09:00"
    assert "Testemunho da Ana: adoro a equipa" in page["lines"]  # the text is current: no warning tomorrow


def test_one_bad_page_never_stops_the_others(tmp_path, monkeypatch, cfg):
    monkeypatch.setattr(link, "_resolve", lambda host: "93.184.216.34")
    db = Database(tmp_path / "t.db")
    db.add_watched("Aaa", "https://example.com:99999/")  # read first (by name)
    db.add_watched("Boa", "https://d.pt/carreiras")
    watch.check_pages(db, cfg, site({("d.pt", "/carreiras"): TEXT}), "2026-11-19T09:00", pause=0)
    by = {p["name"]: p for p in db.watched_pages()}
    assert by["Aaa"]["error"] and by["Aaa"]["checked_at"] == "2026-11-19T09:00"
    assert by["Boa"]["lines"] and not by["Boa"]["error"]


def test_a_robots_txt_that_cant_be_read_means_the_page_isnt_read(tmp_path, monkeypatch, cfg):
    # RFC 9309: a server error (or 401/403) on robots.txt means "assume nothing is allowed"
    monkeypatch.setattr(link, "_resolve", lambda host: "93.184.216.34")
    db = Database(tmp_path / "t.db")
    db.add_watched("Instável", "https://e.pt/jobs")
    db.add_watched("Fechada", "https://f.pt/jobs")
    asked = []

    def handler(request):
        asked.append((request.headers["Host"], request.url.path))
        if request.url.path == "/robots.txt":
            return httpx.Response(503 if request.headers["Host"] == "e.pt" else 403)
        return httpx.Response(200, text=TEXT, headers={"content-type": "text/html"})

    watch.check_pages(db, cfg, httpx.Client(transport=httpx.MockTransport(handler)), "2026-11-19T09:00", pause=0)
    assert ("e.pt", "/jobs") not in asked and ("f.pt", "/jobs") not in asked
    assert all("robots.txt" in p["error"] and not p["lines"] for p in db.watched_pages())


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
                "https://example.com:99999/", "http://[x/",
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
