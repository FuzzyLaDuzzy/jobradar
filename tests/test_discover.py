import httpx

from jobradar.db import Database
from jobradar.discover import run, slugs
from jobradar.models import Job


def test_slugs_drop_legal_suffixes():
    assert slugs("Balanças Marques, S.A.") == ["balancasmarques", "balancas-marques"]
    assert slugs("Uphold") == ["uphold"]


def test_discover_finds_boards_of_companies_in_the_area(tmp_path, make_client):
    db = Database(tmp_path / "t.db")
    for i, (company, location) in enumerate([("Uphold", "Braga"), ("Lisbon Co", "Lisboa"), ("Bosch Group", "Braga")]):
        db.upsert(Job(source="itjobs", external_id=str(i), company=company, title="Developer",
                      location=location, url="u"), 10, [], {}, "2026-11-01")
    cfg = {"search": {"locations": ["braga"]}, "sources": {"smartrecruiters": [{"company": "BoschGroup"}]}}
    hosts = []

    def handler(request):
        hosts.append(str(request.url))
        if str(request.url) == "https://uphold.bamboohr.com/careers/list":
            return httpx.Response(200, json={"result": [{"id": "882", "location": {"city": "Braga"}}]})
        if str(request.url) == "https://f3m.jobs.personio.de/xml":  # Personio answers XML
            return httpx.Response(200, text="<workzag-jobs><position><office>Braga</office></position></workzag-jobs>")
        return httpx.Response(404)

    lines = []
    found = run(cfg, db, make_client(handler), extra=["F3M"], pause=0, out=lines.append)
    assert found == [("F3M", "personio", "f3m", 1, "braga"), ("Uphold", "bamboohr", "uphold", 1, "braga")]
    assert "bamboohr:\n    - name: Uphold\n      site: uphold" in "\n".join(lines)
    # outside the area, or already a source: not probed
    assert not any("lisbon" in h or "bosch" in h for h in hosts)
    assert any("f3m" in h for h in hosts)  # names given on the command line are probed too
