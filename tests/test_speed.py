"""A search reads the platforms at the same time, but never two sources of one platform at once."""

import threading
import time
from types import SimpleNamespace

from jobradar.db import Database
from jobradar.models import Job
from jobradar.refresh import run_refresh


def test_platforms_are_read_at_the_same_time_and_each_one_in_turn(tmp_path):
    both = threading.Barrier(2, timeout=5)  # only passes if Lever and Recruitee are being read at once
    lock = threading.Lock()
    lever_now = lever_most = 0

    def lever(client, entry, prefilter=None):
        nonlocal lever_now, lever_most
        with lock:
            lever_now += 1
            lever_most = max(lever_most, lever_now)
        if entry["site"] == "a":
            both.wait()
        time.sleep(0.05)
        with lock:
            lever_now -= 1
        return [Job(source=f"lever:{entry['site']}", external_id="1", company="Acme", title="Junior Data Engineer",
                    location="Braga", url=f"https://jobs.lever.co/{entry['site']}/1", posted_at="2026-11-01")]

    def recruitee(client, entry, prefilter=None):
        both.wait()
        return []

    cfg = {"search": {"locations": ["braga"], "title_keywords": ["data"]},
           "sources": {"lever": [{"site": "a"}, {"site": "b"}], "recruitee": [{"company": "c"}]},
           "scoring": {"llm": {"enabled": False}}}
    runs = run_refresh(cfg, Database(tmp_path / "t.db"), client=SimpleNamespace(),
                       fetchers={"lever": lever, "recruitee": recruitee})
    assert [r["status"] for r in runs] == ["ok", "ok", "ok"]  # the barrier didn't time out: read at once
    assert [r["source"] for r in runs] == ["lever:a", "lever:b", "recruitee:c"]  # still in the config's order
    assert [r["kept"] for r in runs] == [1, 1, 0]
    assert lever_most == 1  # one platform: one source at a time, as before


def test_a_source_that_breaks_does_not_stop_the_others(tmp_path):
    def broken(client, entry, prefilter=None):
        raise ValueError("the page changed")

    cfg = {"search": {"locations": ["braga"], "title_keywords": ["data"]},
           "sources": {"lever": [{"site": "a"}], "recruitee": [{"company": "c"}]}, "scoring": {"llm": {"enabled": False}}}
    runs = run_refresh(cfg, Database(tmp_path / "t.db"), client=SimpleNamespace(),
                       fetchers={"lever": broken, "recruitee": lambda c, e, prefilter=None: []})
    assert [(r["status"], r["message"]) for r in runs] == [("error", "ValueError: the page changed"), ("ok", "")]
