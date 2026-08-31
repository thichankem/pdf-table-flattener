#!/usr/bin/env bash
# ===================================================================
#  PDF Table Flattener - Linux launcher
#
#  Run it either way:
#    * open a terminal in this folder and type:  ./START_Linux.sh
#    * or double-click it (choose "Run" if asked).
#
#  The first run installs an application-menu entry for the desktop.
# ===================================================================
set -u
APP_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

chmod +x "$APP_ROOT/tools/posix_launch.sh" "$APP_ROOT/START_Linux.sh" 2>/dev/null || true

# A desktop entry is the only way most Linux file managers will let a user
# start this from a menu instead of a terminal, and it costs nothing to write.
install_desktop_entry() {
    local dir="$HOME/.local/share/applications"
    local entry="$dir/pdf-table-flattener.desktop"
    [ -f "$entry" ] && return 0
    mkdir -p "$dir" 2>/dev/null || return 0
    cat > "$entry" <<EOF
[Desktop Entry]
Type=Application
Name=PDF Table Flattener
Comment=Flatten tables in PDF / Word / Excel documents into bullet points
Exec=bash "$APP_ROOT/START_Linux.sh"
Path=$APP_ROOT
Icon=x-office-document
Terminal=false
Categories=Office;Utility;
EOF
    chmod +x "$entry" 2>/dev/null || true
}
install_desktop_entry

exec bash "$APP_ROOT/tools/posix_launch.sh" "$APP_ROOT" --mode gui
