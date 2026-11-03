"""＋ Follow a company from a job card: find its careers site, then add it to `sources` in config.yaml."""

import shutil
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from jobradar import config, discover
from jobradar.app import create_app

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def config_path(tmp_path):
    path = tmp_path / "config.yaml"
    shutil.copy(ROOT / "config.example.yaml", path)
    return path


def test_new_entry_goes_at_the_end_of_its_list(config_path):
    before = config_path.read_text(encoding="utf-8")
    config.add_source("smartrecruiters", {"company": "acmesoftware", "country": "pt"}, config_path)
    after = config_path.read_text(encoding="utf-8")
    added = "    - company: acmesoftware\n      country: pt\n"
    assert after.replace(added, "", 1) == before  # only those two lines are new
    assert after.index(added) < after.index("  lever:")  # inside smartrecruiters, before the next platform
    assert yaml.safe_load(after)["sources"]["smartrecruiters"][-1] == {"company": "acmesoftware", "country": "pt"}


def test_a_platform_not_used_yet_is_added_and_comments_stay(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("search:\n  locations: [braga]\nsources:\n  landingjobs:\n    - feed: https://landing.jobs/feed\n"
                    "  # my notes\n", encoding="utf-8")
    config.add_source("lever", {"site": "acme", "company": "Acme: Software"}, path)
    text = path.read_text(encoding="utf-8")
    assert text.endswith("    - feed: https://landing.jobs/feed\n  lever:\n    - site: acme\n"
                         "      company: \"Acme: Software\"\n  # my notes\n")
    assert yaml.safe_load(text)["sources"]["lever"] == [{"site": "acme", "company": "Acme: Software"}]


def test_find_a_company_and_follow_it(config_path, monkeypatch):
    probed = []

    def fake_probe(client, name, pause, places=()):
        probed.append((name, places))
        return [(name, "smartrecruiters", "acmesoftware", 12, "braga"), (name, "ashby", "acme", 3, None)]

    monkeypatch.setattr(discover, "probe", fake_probe)
    client = TestClient(create_app(config_path=config_path, db_path=config_path.parent / "t.db"))
    data = client.post("/api/discover", json={"company": "Acme Software"}).json()
    assert probed == [("Acme Software", ["braga"])]  # searched with your main place
    assert data["followed"] is False
    sr, ashby = data["found"]
    assert sr == {"platform": "smartrecruiters", "slug": "acmesoftware", "jobs": 12, "place": "Braga",
                  "entry": {"company": "acmesoftware", "country": "pt"}}
    assert ashby["entry"] is None  # a platform the app doesn't read yet

    assert client.post("/api/sources", json={"kind": "smartrecruiters", "entry": sr["entry"]}).json() == {"ok": True}
    assert config.load(config_path)["sources"]["smartrecruiters"][-1] == sr["entry"]
    # now it is followed: no lookup, no request to any platform
    probed.clear()
    assert client.post("/api/discover", json={"company": "acmesoftware"}).json()["followed"] is True
    assert probed == []


def test_only_known_platforms_and_plain_entries(config_path):
    client = TestClient(create_app(config_path=config_path, db_path=config_path.parent / "t.db"))
    before = config_path.read_text(encoding="utf-8")
    assert client.post("/api/sources", json={"kind": "ashby", "entry": {"company": "x"}}).status_code == 400
    for bad in ({"company": "x\nscoring: {}"}, {"url": "https://evil.example"}, {}):
        assert client.post("/api/sources", json={"kind": "lever", "entry": bad}).status_code == 422
    assert config_path.read_text(encoding="utf-8") == before
