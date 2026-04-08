#!/usr/bin/env bash
# TheConstruct — one-line installer for macOS/Linux.
#
# Usage:
#   curl -sSL https://raw.githubusercontent.com/lozturner/theconstruct/claude/multi-agent-orchestration-ipOZM/install.sh | bash
#
# Clones/updates the repo into ~/TheConstruct, makes a venv, installs
# deps, creates a Desktop launcher, and opens the local web app at
# http://localhost:7117/.

set -euo pipefail

REPO="https://github.com/lozturner/theconstruct.git"
BRANCH="claude/multi-agent-orchestration-ipOZM"
DST="$HOME/TheConstruct"
PORT=7117

say() { printf '\033[36m[TheConstruct]\033[0m %s\n' "$*"; }
die() { printf '\033[31m[TheConstruct]\033[0m %s\n' "$*" >&2; exit 1; }

command -v python3 >/dev/null 2>&1 || die "python3 is not installed"
command -v git     >/dev/null 2>&1 || die "git is not installed"

if [ -d "$DST/.git" ]; then
  say "Updating existing install at $DST"
  git -C "$DST" fetch origin "$BRANCH" >/dev/null 2>&1
  git -C "$DST" checkout "$BRANCH"     >/dev/null 2>&1
  git -C "$DST" reset --hard "origin/$BRANCH" >/dev/null 2>&1
else
  say "Cloning into $DST"
  git clone --branch "$BRANCH" --depth 1 "$REPO" "$DST" >/dev/null
fi

cd "$DST"

if [ ! -x "$DST/.venv/bin/python" ]; then
  say "Creating virtual environment"
  python3 -m venv "$DST/.venv"
fi

say "Installing Python dependencies (this takes a minute)"
"$DST/.venv/bin/pip" install --quiet --upgrade pip
"$DST/.venv/bin/pip" install --quiet -r requirements.txt

say "Installing Chromium for Playwright"
"$DST/.venv/bin/python" -m playwright install chromium >/dev/null 2>&1 || true

# Desktop launcher
DESK="$HOME/Desktop"
[ -d "$DESK" ] || DESK="$HOME"

case "$(uname -s)" in
  Darwin)
    cat > "$DESK/TheConstruct.command" <<EOF
#!/bin/sh
cd "$DST"
exec "$DST/.venv/bin/python" "$DST/app.py"
EOF
    chmod +x "$DESK/TheConstruct.command"
    say "Desktop launcher: $DESK/TheConstruct.command"
    ;;
  *)
    cat > "$DESK/TheConstruct.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=TheConstruct
Comment=YouTube link in, Desktop folder out
Exec=$DST/.venv/bin/python $DST/app.py
Terminal=false
Categories=AudioVideo;
EOF
    chmod +x "$DESK/TheConstruct.desktop"
    say "Desktop launcher: $DESK/TheConstruct.desktop"
    ;;
esac

say "Starting TheConstruct at http://localhost:$PORT/ ..."
( "$DST/.venv/bin/python" "$DST/app.py" & ) >/dev/null 2>&1
sleep 1
if command -v open >/dev/null 2>&1; then
  open "http://localhost:$PORT/" >/dev/null 2>&1 || true
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "http://localhost:$PORT/" >/dev/null 2>&1 || true
fi

say "Done. Double-click the Desktop launcher next time."
