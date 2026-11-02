"""Zoho Recruit career sites (used by Edigma and others): careers.<company>.../jobs/Careers.

The page itself carries every published job, with its full description, as JSON in a
hidden field (<input type="hidden" value="[...]" id="jobs">), so one request is enough.
Each job's page is {url}/{id}.
"""

from __future__ import annotations

import html
import json
import re

import httpx

from ..i18n import t
from ..models import Job
from ..text import strip_html
from .base import Prefilter

_JOBS_RE = re.compile(r'<input[^>]*value="(\[[^"]*\])"[^>]*id="jobs"', re.S)


def to_job(name: str, url: str, item: dict) -> Job:
    return Job(
        source=f"zohorecruit:{name}",
        external_id=str(item["id"]),
        company=name,
        title=(item.get("Posting_Title") or item.get("Job_Opening_Name") or "").strip(),
        location=", ".join(dict.fromkeys(p for p in (item.get("City"), item.get("State")) if p)),
        url=f"{url}/{item['id']}",
        posted_at=(item.get("Date_Opened") or "")[:10] or None,
        description=strip_html(item.get("Job_Description")),
        contract=item.get("Job_Type") or "",
        experience=item.get("Work_Experience") or "",
        work_model="remote" if item.get("Remote_Job") else "",
    )


def fetch(client: httpx.Client, entry: dict, prefilter: Prefilter = None) -> list[Job]:
    url, name = entry["url"].rstrip("/"), entry["name"]
    resp = client.get(url)
    resp.raise_for_status()
    match = _JOBS_RE.search(resp.text)
    if not match:
        raise RuntimeError(t("Zoho Recruit: {url} sem a lista de vagas (a página mudou?)", url=url))
    items = json.loads(html.unescape(match.group(1)))
    return [to_job(name, url, item) for item in items if item.get("Publish", True) and item.get("id")]
