#!/usr/bin/env bash
# ===================================================================
#  PDF Table Flattener — trình khởi chạy cho Linux
#
#  Chạy bằng một trong hai cách:
#    • Mở Terminal trong thư mục này rồi gõ:  ./START_Linux.sh
#    • Hoặc nháy đúp chuột (chọn "Run"/"Chạy" nếu được hỏi).
#
#  Lần chạy đầu tiên sẽ tự tạo lối tắt trong menu ứng dụng của hệ thống.
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
Comment=Làm phẳng bảng trong PDF / Word / Excel thành gạch đầu dòng
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
