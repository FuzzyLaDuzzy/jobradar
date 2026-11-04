#!/bin/sh
# JobRadar installer for macOS and Linux:
#   curl -fsSL https://raw.githubusercontent.com/FuzzyLaDuzzy/jobradar/main/install.sh | sh
# Run it again to update: config.yaml, .env, the jobs database and the backups are never touched.
# JOBRADAR_DIR=<folder> to choose where, JOBRADAR_SOURCE=<local copy> instead of downloading, JOBRADAR_YES=1 for no questions.
set -eu
DIR="${JOBRADAR_DIR:-$HOME/.local/share/jobradar}"
REPO="https://github.com/FuzzyLaDuzzy/jobradar"

say() { printf '==> %s\n' "$1"; }
ask() {
    [ "${JOBRADAR_YES:-}" = 1 ] && return 0
    printf '%s [Y/n] ' "$1"
    read -r answer < /dev/tty 2>/dev/null || return 1  # no terminal to ask: no
    case "$answer" in [nN]*) return 1 ;; esac
}

# 1. Python 3.10 or later
PY=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
        PY="$candidate"
        break
    fi
done
[ -n "$PY" ] || { echo "JobRadar needs Python 3.10 or later: https://www.python.org/downloads/ (or your package manager)."; exit 1; }
say "Python: $("$PY" --version)"

# 2. The code (only the code: your settings, keys and jobs stay as they are)
mkdir -p "$DIR"
if [ -n "${JOBRADAR_SOURCE:-}" ]; then
    FROM="$JOBRADAR_SOURCE"
else
    say "Downloading JobRadar from $REPO"
    TMP="$(mktemp -d)"
    curl -fsSL "$REPO/archive/refs/heads/main.tar.gz" | tar -xz -C "$TMP"
    FROM="$TMP/jobradar-main"
fi
rm -rf "$DIR/jobradar"  # files removed upstream go too
cp -R "$FROM/jobradar" "$DIR/"
for file in requirements.txt config.example.yaml .env.example README.md LICENSE; do
    if [ -f "$FROM/$file" ]; then cp "$FROM/$file" "$DIR/"; fi
done
say "Installed in $DIR"

# 3. Its own Python environment and packages
[ -x "$DIR/.venv/bin/python" ] || { say "Creating the Python environment"; "$PY" -m venv "$DIR/.venv"; }
say "Installing the packages (a minute or two the first time)"
"$DIR/.venv/bin/python" -m pip install --disable-pip-version-check --quiet -r "$DIR/requirements.txt"

# 4. A `jobradar` command, and optionally the daily searches
mkdir -p "$HOME/.local/bin"
printf '#!/bin/sh\ncd "%s" && exec .venv/bin/python -m jobradar "$@"\n' "$DIR" > "$HOME/.local/bin/jobradar"
chmod +x "$HOME/.local/bin/jobradar"
say "Added the jobradar command in ~/.local/bin"
if command -v crontab >/dev/null 2>&1 && ask "Search for new jobs every day at 9:00 and 21:00 (cron)?"; then
    { crontab -l 2>/dev/null | grep -v 'jobradar refresh' || true
      echo "0 9,21 * * * cd \"$DIR\" && .venv/bin/python -m jobradar refresh >> jobradar.log 2>&1"; } | crontab -
    say "Daily searches set up (crontab -l to see them)"
fi

say "Done. Run: jobradar   (if the command isn't found, add ~/.local/bin to your PATH)"
say "To update later, run the same line again. To uninstall: delete $DIR, ~/.local/bin/jobradar and the cron line."
