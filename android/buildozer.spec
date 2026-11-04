# JobRadar as an Android app that runs on the phone by itself: python-for-android packs Python, the
# jobradar package and its requirements into the APK. Built by .github/workflows/android.yml.

[app]
title = JobRadar
package.name = jobradar
package.domain = io.github.fuzzyladuzzy
version = 0.1.0

source.dir = .
source.include_exts = py,html,js,css,json,yaml,png,svg,ico
source.exclude_dirs = bin,.buildozer,__pycache__

# requirements.txt, pinned, plus what those packages pull in (python-for-android doesn't resolve them).
# pydantic-core is Rust: python-for-android compiles it with its own recipe (2.41.4), and pydantic 2.12.3
# is the release made for that version. No anthropic: on the phone the AI is Gemini, over httpx.
# pyjnius: main.py opens the app's window with the key (PythonActivity.loadUrl).
requirements = python3,hostpython3,sqlite3,openssl,pyjnius,pydantic-core,pydantic==2.12.3,annotated-types==0.8.0,typing-inspection==0.4.4,typing-extensions==4.16.0,fastapi==0.162.0,starlette==1.10.0,annotated-doc==0.0.5,opentelemetry-api==1.45.2,uvicorn==0.54.0,h11==0.16.0,click==8.5.0,anyio==4.16.0,idna==3.20,httpx==0.28.1,httpcore==1.0.9,certifi==2026.10.23,pyyaml==6.0.3

icon.filename = %(source.dir)s/jobradar/static/icon-512.png
orientation = portrait
fullscreen = 0

android.permissions = INTERNET
# Java added to the app: the file chooser for the CV (the window has none of its own)
android.add_src = %(source.dir)s/java
# 34, not 35: from 35 Android draws apps under the status bar, and the webview bootstrap doesn't leave room
android.api = 34
android.minapi = 24
android.ndk = 28c
# arm64-v8a: phones. CI also builds x86_64 for its emulator, as a build of its own (APP_ANDROID_ARCHS):
# python-for-android builds every arch in one venv, and making it again for the second arch puts
# the bundled pip back over the upgraded one, half-mixed (pip >= 26.2 then fails to import)
android.archs = arm64-v8a
# a release build gives an .apk to install, not the Play Store's .aab
android.release_artifact = apk
android.accept_sdk_license = True
# keeps the .env (API keys) out of Google's cloud backups
android.allow_backup = False

p4a.branch = v2026.05.09
p4a.bootstrap = webview
p4a.port = 8000

[buildozer]
log_level = 2
warn_on_root = 1
