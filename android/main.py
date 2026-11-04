"""JobRadar on Android. python-for-android's webview bootstrap runs this file; its loading screen waits
for port 8000 (p4a.port in buildozer.spec) and opens it once. Links to other sites open in the browser.

On a phone every other app can reach 127.0.0.1 too, so the API answers only this app's window: it
gets a key made at each start (create_app(token=...)), which only this process and the window know.

The build copies the jobradar package and config.example.yaml next to this file
(.github/workflows/android.yml), so the phone runs the same code as the computer.
"""

import logging
import os
import secrets
import socket
import threading
from pathlib import Path
from urllib.parse import quote

# config.yaml, .env and jobradar.db live in the app's private storage, which other apps can't read,
# and outside the code folder ($ANDROID_PRIVATE/app), which an update replaces
home = Path(os.environ["ANDROID_PRIVATE"]) / "data"
home.mkdir(parents=True, exist_ok=True)
os.chdir(home)

import uvicorn  # noqa: E402
from jnius import autoclass  # noqa: E402

from jobradar import config as config_mod  # noqa: E402
from jobradar.app import create_app  # noqa: E402
from jobradar.i18n import t  # noqa: E402

PORT = 8000
window = autoclass("org.kivy.android.PythonActivity")
autoclass("org.kivy.android.JobRadarFilePicker").install()  # "choose your CV" opens Android's picker

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)  # the ITJobs URL carries the api_key
config_mod.load_dotenv()
config_mod.ensure()
try:
    config_mod.load()  # the app's language
except (OSError, config_mod.ConfigError):
    pass  # the app shows it

# bound here: if another app already holds the port, the window must not stay on that app's pages
sock = socket.socket()
try:
    sock.bind(("127.0.0.1", PORT))
except OSError:
    message = t("Outra app já usa a porta {port} deste telemóvel. Fecha-a e abre o JobRadar outra vez.", port=PORT)
    window.loadUrl("data:text/html;charset=utf-8," + quote(f"<p style='font:18px sans-serif;margin:24px'>{message}</p>"))
    raise

token = secrets.token_urlsafe(32)
app = create_app(token=token)


def open_window():
    # the loading screen opens / once, without the key; after that, this visit is the last one
    app.state.opened.wait(30)
    window.loadUrl(f"http://127.0.0.1:{PORT}/?k={token}")


threading.Thread(target=open_window, daemon=True).start()
uvicorn.Server(uvicorn.Config(app, log_level="warning")).run(sockets=[sock])
