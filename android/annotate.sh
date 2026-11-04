#!/usr/bin/env bash
# The end of a log as the run's annotations, which can be read without signing in to GitHub (its logs
# can't). Leaves out buildozer's dump of the environment after a failure; an annotation holds about
# 4 KB, so the end goes in pieces of 20 lines.  Usage: annotate.sh <log> <title>
sed 's/\x1b\[[0-9;]*m//g' "$1" | sed '/Buildozer failed to execute the last command/,$d' | tail -n 160 | cut -c1-200 > /tmp/tail.txt
split -l 20 /tmp/tail.txt /tmp/part.
for f in /tmp/part.*; do
  echo "::error title=$2 ${f##*.}::$(awk 'BEGIN { ORS = "%0A" } { gsub(/%/, "%25"); gsub(/\r/, ""); print }' "$f")"
done
