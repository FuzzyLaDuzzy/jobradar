"""JobRadar on Android. python-for-android's webview bootstrap runs this file and, once the port
answers, shows http://127.0.0.1:8000 in the app's window; links to other sites open in the browser.

The build copies the jobradar package and config.example.yaml next to this file
(.github/workflows/android.yml), so the phone runs the same code as the computer.
"""

import os
import sys
from pathlib import Path

# config.yaml, .env and jobradar.db live in the app's private storage, which other apps can't read,
# and outside the code folder ($ANDROID_PRIVATE/app), which an update replaces
home = Path(os.environ["ANDROID_PRIVATE"]) / "data"
home.mkdir(parents=True, exist_ok=True)
os.chdir(home)
sys.argv = ["jobradar", "--no-browser"]  # the app's window is the browser

from jobradar.__main__ import main  # noqa: E402

main()
