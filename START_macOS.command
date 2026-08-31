#!/usr/bin/env bash
# ===================================================================
#  PDF Table Flattener - macOS launcher
#  Double-click this file to run the app.
#
#  If macOS says "cannot be opened because it is from an unidentified
#  developer": RIGHT-CLICK the file -> Open -> Open. Once is enough.
# ===================================================================
set -u
APP_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# A folder that arrived by download or AirDrop is quarantined, and every script
# inside it is refused until the flag is cleared.  Clearing it for our own
# folder is what the user would otherwise be told to type by hand.
if command -v xattr >/dev/null 2>&1; then
    xattr -dr com.apple.quarantine "$APP_ROOT" >/dev/null 2>&1 || true
fi

chmod +x "$APP_ROOT/tools/posix_launch.sh" 2>/dev/null || true
exec bash "$APP_ROOT/tools/posix_launch.sh" "$APP_ROOT" --mode gui
