#!/usr/bin/env bash
# On the emulator: install the APK, open the app and check that its server answers, that the API
# refuses other apps, and that the app's window got in with the key (read here from the log, which
# only adb and the app itself can read). Leaves screen.png and logcat.txt for the CI artifacts.
set -u
adb install -r "$(ls android/bin/*.apk | head -1)"
adb shell am start -n io.github.fuzzyladuzzy.jobradar/org.kivy.android.PythonActivity
adb forward tcp:8000 tcp:8000

status=1
for _ in $(seq 1 60); do
  url=$(adb logcat -d | grep -o "Opening URL: http://127.0.0.1:8000/?k=[A-Za-z0-9_-]*" | tail -1 | cut -d' ' -f3)
  if [ -n "$url" ]; then status=0; break; fi
  sleep 3
done
check() { echo "$1"; [ "$2" = "$3" ] || { echo "  expected $3, got $2"; status=1; }; }
if [ "$status" = 0 ]; then
  check "the page" "$(curl -s http://127.0.0.1:8000/ | grep -c '<title>JobRadar')" 1
  check "the API, from another app" "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/api/jobs)" 403
  check "the app's window opens with the key" "$(curl -s -c jar -o /dev/null -w '%{http_code}' "$url")" 303
  check "then the API answers" "$(curl -s -b jar http://127.0.0.1:8000/api/jobs)" "[]"
  sleep 10  # the window switches from the loading screen to the app
else
  echo "the app never opened its window"
fi
adb exec-out screencap -p > screen.png
adb logcat -d > logcat.txt
grep -E " python *:" logcat.txt | tail -60
exit "$status"
