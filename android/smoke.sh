#!/usr/bin/env bash
# On the emulator: install the APK, open the app and check that its server answers.
# Leaves screen.png (what the app shows) and logcat.txt (Python's output) for the CI artifacts.
set -u
adb install -r "$(ls android/bin/*.apk | head -1)"
adb shell am start -n io.github.fuzzyladuzzy.jobradar/org.kivy.android.PythonActivity
adb forward tcp:8000 tcp:8000

status=1
for _ in $(seq 1 60); do
  if curl -sf http://127.0.0.1:8000/api/jobs > /dev/null; then status=0; break; fi
  sleep 3
done
if [ "$status" = 0 ]; then
  curl -sf http://127.0.0.1:8000/ | grep -q JobRadar || status=1
  echo "jobs: $(curl -s http://127.0.0.1:8000/api/jobs)"
  sleep 10  # the window switches from the loading page to the app
fi
adb exec-out screencap -p > screen.png
adb logcat -d > logcat.txt
grep -E " python *:" logcat.txt | tail -60
exit "$status"
