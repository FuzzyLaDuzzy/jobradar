"""Windows notification when a refresh finds new jobs (the scheduled task runs with no window).

Uses the toast API that ships with Windows, through PowerShell: no extra dependency.
Job titles come from job sites, so they never go inside the PowerShell code: the
toast XML travels in an environment variable that the script only reads as data.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from .i18n import t

try:
    import winreg
except ImportError:  # not Windows
    winreg = None

log = logging.getLogger("jobradar")

# The toasts show this id's name and icon, registered per user (no admin; delete the key to undo).
APP_ID = "JobRadar"
REGISTRY_KEY = rf"Software\Classes\AppUserModelId\{APP_ID}"
ICON = Path(__file__).parent / "static" / "icon-192.png"
SCRIPT = (
    "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null;"
    "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] > $null;"
    "$xml = New-Object Windows.Data.Xml.Dom.XmlDocument; $xml.LoadXml($env:JOBRADAR_TOAST);"
    f"[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{APP_ID}')"
    ".Show([Windows.UI.Notifications.ToastNotification]::new($xml))"
)


def _line(job: dict) -> str:
    return f"{job['title']} · {job['company']}" if job.get("company") else job["title"]


def toast_xml(jobs: list[dict], url: str) -> str:
    """Title plus the two best jobs: a toast shows at most three lines of text."""
    head = t("1 vaga nova") if len(jobs) == 1 else t("{n} vagas novas", n=len(jobs))
    lines = [f"JobRadar: {head}"] + [_line(j) for j in jobs[:2]]
    if len(jobs) > 2:
        lines[-1] += t(" (e mais {n})", n=len(jobs) - 2)
    texts = "".join(f"<text>{escape(line)}</text>" for line in lines)
    return (f'<toast activationType="protocol" launch={quoteattr(url)}>'
            f'<visual><binding template="ToastGeneric">{texts}</binding></visual></toast>')


def register() -> None:
    """Tell Windows the name and icon to show on JobRadar's toasts."""
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY) as key:
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, "JobRadar")
        winreg.SetValueEx(key, "IconUri", 0, winreg.REG_SZ, str(ICON))


def show(jobs: list[dict], url: str) -> None:
    if not jobs or sys.platform != "win32":
        return
    try:
        register()
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", SCRIPT],
            env={**os.environ, "JOBRADAR_TOAST": toast_xml(jobs, url)},
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=30, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:  # a missing toast must never break a refresh
        log.warning("Não foi possível mostrar a notificação: %s", exc)
