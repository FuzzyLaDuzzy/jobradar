"""The area is written once, in `search`, and the sources that search by place use it."""

import json

import httpx

from jobradar import config
from jobradar.sources import itjobs, successfactors, with_area, workday

SEARCH = {"locations_primary": ["lisboa", "lisbon"], "locations": ["lisboa", "lisbon", "oeiras"]}


def test_sources_take_the_area_from_search_unless_the_entry_has_its_own():
    assert with_area("workday", {"url": "u"}, SEARCH)["search"] == ["lisboa", "lisbon"]
    assert with_area("workday", {"url": "u", "search": ""}, SEARCH)["search"] == ""  # "" = every job
    assert with_area("successfactors", {"url": "u"}, SEARCH)["location"] == ["lisboa", "lisbon"]
    assert with_area("itjobs", {}, SEARCH)["location_names"] == ["lisboa", "lisbon", "oeiras"]
    assert with_area("lever", {"site": "x"}, SEARCH) == {"site": "x"}
    # no primary places: the first accepted one
    assert with_area("workday", {"url": "u"}, {"locations": ["porto", "maia"]})["search"] == ["porto"]


def test_itjobs_finds_the_district_ids_by_name(make_client):
    calls = []

    def handler(request):
        calls.append((request.url.path, dict(request.url.params)))
        if request.url.path == "/location/list.json":
            return httpx.Response(200, json={"total": 3, "results": [
                {"id": 4, "name": "Braga"}, {"id": 14, "name": "Lisboa"}, {"id": 10, "name": "Évora"}]})
        return httpx.Response(200, json={"total": 0, "results": []})

    itjobs.fetch(make_client(handler), with_area("itjobs", {"professional_internships": False}, SEARCH),
                 api_key="k")
    assert [(path, params.get("location")) for path, params in calls] == [
        ("/location/list.json", None), ("/job/list.json", "14")]
    # ids written in the entry win, and then the list of districts isn't needed
    calls.clear()
    itjobs.fetch(make_client(handler), with_area("itjobs", {"locations": [4], "professional_internships": False},
                                                  SEARCH), api_key="k")
    assert [path for path, _ in calls] == ["/job/list.json"]
    assert itjobs.district_ids(make_client(handler), "k", ["evora"]) == [10]  # accents optional


def test_workday_searches_each_place_once_per_job(make_client):
    searched = []

    def handler(request):
        if request.method == "POST":
            text = json.loads(request.content)["searchText"]
            searched.append(text)
            postings = [{"title": "Data Engineer", "externalPath": "/job/Lisbon/Data-Engineer_R1",
                         "locationsText": "Lisbon", "bulletFields": ["R1"]}]
            if text == "lisboa":
                postings.append({"title": "QA Analyst", "externalPath": "/job/Lisboa/QA_R2",
                                 "locationsText": "Lisboa", "bulletFields": ["R2"]})
            return httpx.Response(200, json={"total": len(postings), "jobPostings": postings})
        return httpx.Response(200, json={"jobPostingInfo": {}})

    jobs = workday.fetch(make_client(handler), with_area("workday", {
        "name": "Accenture", "url": "https://accenture.wd103.myworkdayjobs.com/AccentureCareers"}, SEARCH))
    assert searched == ["lisboa", "lisbon"]
    assert [j.external_id for j in jobs] == ["R1", "R2"]  # R1 came back twice


def test_successfactors_sitemap_with_several_places(make_client):
    sitemap = """<urlset>
<url><loc>https://careers.ey.com/job/Lisboa-Auditor-Junior/101/</loc></url>
<url><loc>https://careers.ey.com/job/Lisbon-Data-Analyst/102/</loc></url>
<url><loc>https://careers.ey.com/job/Porto-Tax-Consultant/103/</loc></url>
</urlset>"""

    def handler(request):
        return httpx.Response(200, text=sitemap if request.url.path == "/sitemap.xml" else "")

    jobs = successfactors.fetch(make_client(handler), with_area("successfactors", {
        "name": "EY", "url": "https://careers.ey.com", "sitemap": True}, SEARCH))
    assert [(j.external_id, j.location, j.title) for j in jobs] == [
        ("101", "Lisboa", "Auditor Junior"), ("102", "Lisbon", "Data Analyst")]


def test_successfactors_search_once_per_place(make_client):
    searched = []

    def handler(request):
        searched.append(request.url.params.get("locationsearch"))
        return httpx.Response(200, text="<table></table>")

    successfactors.fetch(make_client(handler), with_area("successfactors", {
        "name": "Deloitte", "url": "https://jobs.deloitte.pt"}, SEARCH))
    assert searched == ["lisboa", "lisbon"]


def test_first_run_starts_from_the_example(tmp_path):
    path = tmp_path / "config.yaml"
    assert config.ensure(path) is True
    assert path.read_text(encoding="utf-8") == config.EXAMPLE.read_text(encoding="utf-8")
    path.write_text("mine", encoding="utf-8")
    assert config.ensure(path) is False  # never overwrites yours
    assert path.read_text(encoding="utf-8") == "mine"
