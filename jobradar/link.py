"""Read a job from its link, for "+ Add job": most careers sites embed the posting as schema.org JobPosting
(for Google Jobs), with title, company, place, date and text; without it, the page's own title and description.

Only on request, one page at a time. LinkedIn, Indeed and Glassdoor are not opened: their terms forbid it.
"""

from __future__ import annotations

import html
import ipaddress
import json
import re
import socket
from urllib.parse import urljoin, urlsplit

import httpx

from .i18n import t
from .text import strip_html

BLOCKED = ("linkedin.com", "indeed.", "glassdoor.")
MAX_BYTES = 3_000_000
MAX_REDIRECTS = 5
_LD_RE = re.compile(r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>", re.S | re.I)


class LinkError(RuntimeError):
    """The page could not be read."""


def _meta(page: str, name: str) -> str:
    for pattern in (rf'<meta[^>]+(?:property|name)=["\']{name}["\'][^>]+content=["\']([^"\']*)',
                    rf'<meta[^>]+content=["\']([^"\']*)["\'][^>]+(?:property|name)=["\']{name}["\']'):
        match = re.search(pattern, page, re.I)
        if match:
            return html.unescape(match.group(1)).strip()
    return ""


def _postings(data) -> list[dict]:
    """Every JobPosting in a JSON-LD block: alone, in a list or in an @graph."""
    items = data if isinstance(data, list) else [data]
    found = []
    for item in items:
        if not isinstance(item, dict):
            continue
        kind = item.get("@type")
        if kind == "JobPosting" or (isinstance(kind, list) and "JobPosting" in kind):
            found.append(item)
        found += _postings(item.get("@graph") or [])
    return found


def _name(value) -> str:
    if isinstance(value, dict):
        return str(value.get("name") or "")
    return str(value or "")


def _place(posting: dict) -> str:
    places = posting.get("jobLocation") or []
    parts: list[str] = []
    for place in places if isinstance(places, list) else [places]:
        address = (place or {}).get("address") if isinstance(place, dict) else None
        if isinstance(address, str):
            parts.append(address)
        elif isinstance(address, dict):
            parts += [_name(address.get(k)) for k in ("addressLocality", "addressRegion", "addressCountry")]
    if posting.get("jobLocationType") == "TELECOMMUTE":
        parts.append("Remote")
    seen: list[str] = []
    for part in (p.strip() for p in parts):
        if part and part not in seen:
            seen.append(part)
    return ", ".join(seen)


def parse(page: str) -> dict:
    """The job's fields from a page's HTML (empty strings for what it doesn't say)."""
    for block in _LD_RE.findall(page):
        try:
            data = json.loads(block.strip())
        except ValueError:
            continue
        for posting in _postings(data):
            return {"title": strip_html(html.unescape(str(posting.get("title") or ""))),
                    "company": _name(posting.get("hiringOrganization")),
                    "location": _place(posting),
                    "posted_at": str(posting.get("datePosted") or "")[:10],
                    "description": strip_html(html.unescape(str(posting.get("description") or "")))}
    title = _meta(page, "og:title")
    if not title:
        match = re.search(r"<title[^>]*>(.*?)</title>", page, re.S | re.I)
        title = html.unescape(match.group(1)).strip() if match else ""
    return {"title": title, "company": _meta(page, "og:site_name"), "location": "", "posted_at": "",
            "description": _meta(page, "og:description") or _meta(page, "description")}


def _resolve(host: str) -> str | None:
    """The address to connect to, when every address the name has is on the internet (not this computer, the home
    network or the cloud's metadata address); else None. The request then goes to this very address, so a name
    that answers differently a second time (DNS rebinding) can't send it elsewhere. A name that can't be found
    (no network, a typo) is a LinkError of its own."""
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError):
        raise LinkError(t("Não foi possível encontrar o site {host} (sem rede ou nome errado).", host=host)) from None
    ips = [info[4][0].split("%")[0] for info in infos]
    return ips[0] if ips and all(ipaddress.ip_address(ip).is_global for ip in ips) else None


def _address(url: str) -> str:
    """The checked address to connect to for `url`: a web link (http/https), not a site that forbids programs,
    not this computer or the home network."""
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        parts.port  # noqa: B018 (a port out of range raises here, not later in the request)
    except ValueError:
        raise LinkError(t("Este link não é um endereço válido.")) from None
    if parts.scheme not in ("http", "https") or not host:
        raise LinkError(t("o link tem de começar por http:// ou https://"))
    if any(name in host for name in BLOCKED):
        raise LinkError(t("Este site não deixa ler as vagas por programas: preenche os campos à mão."))
    ip = _resolve(host)
    if ip is None:
        raise LinkError(t("Este link aponta para um endereço local ou privado: a app não o abre."))
    return ip


def _fetch(url: str, client: httpx.Client) -> tuple[str, str]:
    """The page and its final address. Redirects are followed one by one so every hop is checked, and the
    reading stops as soon as the page passes MAX_BYTES."""
    for _ in range(MAX_REDIRECTS + 1):
        ip = _address(url)
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        # to the checked address, with the site's name where the server and TLS (certificate, SNI) expect it
        name = host + (f":{parts.port}" if parts.port else "")
        target = parts._replace(netloc=(f"[{ip}]" if ":" in ip else ip) + (f":{parts.port}" if parts.port else ""))
        # a web page, whatever the client asks the APIs for (JSON): careers sites answer that with 406 or 404
        with client.stream("GET", target.geturl(), extensions={"sni_hostname": host},
                           headers={"Host": name, "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"},
                           follow_redirects=False) as resp:
            if resp.is_redirect:
                url = urljoin(url, resp.headers.get("location", ""))
                continue
            resp.raise_for_status()
            if int(resp.headers.get("content-length") or 0) > MAX_BYTES:
                raise LinkError(t("A página é grande demais para ler."))
            chunks, total = [], 0
            for chunk in resp.iter_bytes():
                total += len(chunk)
                if total > MAX_BYTES:
                    raise LinkError(t("A página é grande demais para ler."))
                chunks.append(chunk)
            return b"".join(chunks).decode(resp.encoding or "utf-8", errors="replace"), url
    raise LinkError(t("O link redireciona vezes demais."))


def read(url: str, client: httpx.Client) -> dict:
    try:
        page, final = _fetch(url, client)
    except httpx.HTTPError as exc:
        raise LinkError(t("Não foi possível abrir o link ({error}).", error=type(exc).__name__)) from exc
    job = parse(page)
    if not job["title"]:
        raise LinkError(t("Não encontrei uma vaga nesta página: preenche os campos à mão."))
    limits = {"title": 200, "company": 200, "location": 200, "posted_at": 10, "description": 20000}
    return {key: value[:limits[key]] for key, value in job.items()} | {"url": final}
