#!/usr/bin/env bash
# Shared launcher body for macOS (START_macOS.command) and Linux
# (START_Linux.sh).  The two wrappers differ only in what a double-click needs
# from the desktop environment, so the actual work lives here in one copy.
#
# Usage: posix_launch.sh <app-root> [--mode gui|cli|test|setup] [args...]

set -u

APP_ROOT="$1"
shift
cd "$APP_ROOT" || { echo "Cannot enter the application folder: $APP_ROOT"; exit 1; }

MODE_ARGS=("$@")
[ ${#MODE_ARGS[@]} -eq 0 ] && MODE_ARGS=(--mode gui)

BOOTSTRAP="$APP_ROOT/tools/bootstrap.py"

die() {
    echo ""
    echo "ERROR: $*"
    echo ""
    # A double-clicked window closes the instant the script ends, taking the
    # error message with it -- so hold it open when there is a terminal to hold.
    if [ -t 0 ]; then
        read -r -p "Press Enter to close..." _ || true
    fi
    exit 1
}

# --- Already set up?  Then skip straight to the app, no network needed. -------
if [ -x "$APP_ROOT/.venv/bin/python" ]; then
    exec "$APP_ROOT/.venv/bin/python" "$BOOTSTRAP" "${MODE_ARGS[@]}"
fi

# --- Find a usable system Python ---------------------------------------------
# tkinter is the part that is genuinely often missing (Linux splits it into
# python3-tk, and it is absent from some minimal macOS setups), so it is
# checked here rather than discovered later as a crash.
PYEXE=""
for candidate in python3 python3.13 python3.12 python3.11 python3.10 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        if "$candidate" -c 'import sys,tkinter; raise SystemExit(0 if sys.version_info>=(3,10) else 1)' >/dev/null 2>&1; then
            PYEXE="$(command -v "$candidate")"
            break
        fi
    fi
done

# --- Nothing usable: fetch a private Python just for this app -----------------
if [ -z "$PYEXE" ]; then
    cat <<'BANNER'

===================================================================
  No suitable Python was found on this machine.
  Downloading a private copy of Python just for this app.
  This runs ONCE and needs an Internet connection.
===================================================================

BANNER
    UV=""
    for uv_path in "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv" "$(command -v uv 2>/dev/null || true)"; do
        [ -n "$uv_path" ] && [ -x "$uv_path" ] && { UV="$uv_path"; break; }
    done

    if [ -z "$UV" ]; then
        echo "[1/2] Downloading the installer..."
        if command -v curl >/dev/null 2>&1; then
            curl -LsSf https://astral.sh/uv/install.sh | sh || true
        elif command -v wget >/dev/null 2>&1; then
            wget -qO- https://astral.sh/uv/install.sh | sh || true
        else
            die "neither curl nor wget is available. Install Python 3.10+ manually from https://www.python.org/downloads/"
        fi
        for uv_path in "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv"; do
            [ -x "$uv_path" ] && { UV="$uv_path"; break; }
        done
    fi

    [ -n "$UV" ] || die "the automatic installer could not be downloaded.
Install Python 3.10+ manually:
  * macOS : https://www.python.org/downloads/macos/
  * Linux : sudo apt install python3 python3-venv python3-tk
Then run this file again."

    echo "[2/2] Installing Python 3.12..."
    "$UV" python install 3.12 || die "Python 3.12 could not be installed."
    PYEXE="$("$UV" python find 3.12 2>/dev/null || true)"
    [ -n "$PYEXE" ] && [ -x "$PYEXE" ] || die "the freshly installed Python could not be found."
fi

# --- Hand over to the cross-platform bootstrap --------------------------------
"$PYEXE" "$BOOTSTRAP" "${MODE_ARGS[@]}"
status=$?
if [ $status -ne 0 ]; then
    echo ""
    echo "The application exited with an error (status $status). See the message above."
    if [ -t 0 ]; then
        read -r -p "Press Enter to close..." _ || true
    fi
fi
exit $status
