"""Usage:
    python -m jobradar                 # opens the app in a window of its own (http://127.0.0.1:8000)
    python -m jobradar refresh         # only updates the jobs (for cron or the Task Scheduler)
    python -m jobradar discover        # finds the careers sites of companies in your area
"""

from __future__ import annotations

import argparse
import logging
import os
import socket
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

from . import config as config_mod
from .db import Database
from .i18n import t
from .refresh import run_refresh

# Opened with --app: a window of its own, without tabs or address bar. The job links
# open in the same browser. Windows paths; elsewhere a normal browser tab opens.
APP_BROWSERS = [
    r"%LocalAppData%\BraveSoftware\Brave-Browser\Application\brave.exe",
    r"%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe",
    r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
    r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
    r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
    r"%LocalAppData%\Google\Chrome\Application\chrome.exe",
]


def open_window(url: str) -> None:
    for path in map(os.path.expandvars, APP_BROWSERS):
        if os.path.exists(path):
            subprocess.Popen([path, f"--app={url}"])
            return
    webbrowser.open(url)  # no Edge or Chrome: a normal browser tab


def already_running(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def main() -> None:
    parser = argparse.ArgumentParser(prog="jobradar")
    parser.add_argument("command", nargs="?", default="serve", choices=["serve", "refresh", "discover", "descobrir"])
    parser.add_argument("names", nargs="*", help="discover: company names to look up besides the ones already seen")
    parser.add_argument("--config", default=str(config_mod.DEFAULT_CONFIG))
    parser.add_argument("--db", default="jobradar.db")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    if sys.stdout is None:  # pythonw (Windows startup, scheduled task): no console, so write to a log
        sys.stdout = sys.stderr = open("jobradar.log", "a", encoding="utf-8", buffering=1)
    else:  # a console or pipe that is not UTF-8 (cp1252) can't print every symbol (⚙): show "?", don't crash
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):  # Android's log stream (python-for-android) has none
                stream.reconfigure(errors="replace")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    # httpx logs every URL at INFO, and the ITJobs URL carries the api_key
    logging.getLogger("httpx").setLevel(logging.WARNING)
    config_mod.load_dotenv()
    created = config_mod.ensure(args.config)
    try:
        config_mod.load(args.config)  # sets the language of everything below
    except (OSError, config_mod.ConfigError):
        pass  # the commands below report it
    if created:
        print(t("Criei {path} a partir do exemplo: muda a zona, a área e o perfil no ⚙ da app ou no ficheiro.",
                path=args.config))

    if args.command == "refresh":
        from datetime import datetime, timezone

        from . import notify

        cfg = config_mod.load(args.config)
        db = Database(args.db)
        db.backup(Path(args.db).resolve().parent / "backups")  # before the refresh touches anything
        started = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for run in run_refresh(cfg, db):
            line = f"{run['source']:<32} {run['status']:<8} {t('lidas')}={run['fetched']:<4} "
            line += f"{t('mantidas')}={run['kept']:<4} {t('novas')}={run['new']}"
            if run.get("message"):
                line += f"  ({run['message']})"
            print(line)
        notify.show(db.new_since(started), f"http://{args.host}:{args.port}")
        return

    if args.command in ("discover", "descobrir"):
        from .discover import run as discover
        from .sources import make_client

        with make_client() as client:
            discover(config_mod.load(args.config), Database(args.db), client, args.names)
        return

    url = f"http://{args.host}:{args.port}"
    if already_running(args.host, args.port):  # opened again from the shortcut: just show the window
        if not args.no_browser:
            open_window(url)
        return

    import uvicorn

    from .app import ALLOWED_HOSTS, create_app

    app = create_app(config_path=args.config, db_path=args.db, allowed_hosts=[*ALLOWED_HOSTS, args.host])
    if not args.no_browser:
        threading.Timer(1.2, lambda: open_window(url)).start()
    print(t("JobRadar a correr em {url}  (Ctrl+C para parar)", url=url))
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
