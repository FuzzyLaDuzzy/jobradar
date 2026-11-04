"""JobRadar.exe: the app with Python inside, made by PyInstaller and installed by windows/JobRadar.iss.

The program's files go in the install folder; config.yaml, .env, jobradar.db and the backups in
%LOCALAPPDATA%\\JobRadar, the folder the one-line installer uses too, so both find the same data.
"""

import os
from pathlib import Path

home = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "JobRadar"
home.mkdir(parents=True, exist_ok=True)
os.chdir(home)  # started from the Start menu, or by the scheduled search, the current folder could be any

from jobradar.__main__ import main  # noqa: E402

main()
