"""Install the optional local LLM (Ollama + the model) on any of the three OSes.

This is deliberately a *separate* step from the app's own setup.  The model is
several gigabytes, the app is fully functional without it, and nobody should
have to wait for a download they may not want.  Everything here is opt-in and
runs only when the user starts this script.

Nothing leaves the machine at run time: Ollama serves the model from localhost,
which is the whole point of using it instead of a hosted API for documents that
may be confidential.
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Optional

for _stream in (sys.stdout, sys.stderr):
    try:  # a Windows console still defaults to cp1252, which cannot print this
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):  # pragma: no cover - odd stream
        pass

APP_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_ROOT))

from src.pdf_table_tool.platform_support import (  # noqa: E402
    IS_MACOS,
    IS_WINDOWS,
    ollama_executable,
    ollama_running,
    open_url,
    start_ollama_server,
)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5vl:7b")

WINDOWS_INSTALLER = "https://ollama.com/download/OllamaSetup.exe"
MACOS_DOWNLOAD_PAGE = "https://ollama.com/download/mac"
LINUX_INSTALL_SCRIPT = "https://ollama.com/install.sh"


def step(message: str) -> None:
    print(f"\n==> {message}", flush=True)


def log(message: str) -> None:
    print(f"  {message}", flush=True)


def confirm(question: str, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    try:
        return input(f"{question} [y/N] ").strip().lower() in ("y", "yes", "c", "co")
    except EOFError:
        return False


# ─────────────────────────────────────── install Ollama ────────────────────────


def install_windows(assume_yes: bool) -> bool:
    if not confirm(
        f"Tải và chạy bộ cài Ollama chính thức từ {WINDOWS_INSTALLER}?", assume_yes
    ):
        return False
    step("Đang tải bộ cài Ollama cho Windows")
    target = Path(tempfile.gettempdir()) / "OllamaSetup.exe"
    try:
        urllib.request.urlretrieve(WINDOWS_INSTALLER, target)
    except OSError as exc:
        log(f"không tải được: {exc}")
        return False
    log(f"đã tải: {target}")
    step("Đang mở bộ cài — hãy làm theo hướng dẫn trên màn hình")
    subprocess.run([str(target)], check=False)
    return ollama_executable() is not None


def install_macos(assume_yes: bool) -> bool:
    # Homebrew, when present, is both the least surprising route and the one
    # that keeps Ollama updated with everything else on the machine.
    if shutil.which("brew"):
        if confirm("Cài Ollama bằng Homebrew (brew install ollama)?", assume_yes):
            step("Đang cài Ollama qua Homebrew")
            if subprocess.run(["brew", "install", "ollama"]).returncode == 0:
                return True
            log("Homebrew không cài được, chuyển sang tải thủ công")

    step("Cần tải Ollama cho macOS thủ công")
    log("Trang tải sẽ mở trong trình duyệt.")
    log("Hãy tải file .dmg, kéo Ollama vào Applications, mở nó lên,")
    log("rồi chạy lại script này để tải mô hình.")
    open_url(MACOS_DOWNLOAD_PAGE)
    return False


def install_linux(assume_yes: bool) -> bool:
    if not confirm(
        f"Chạy script cài đặt chính thức của Ollama ({LINUX_INSTALL_SCRIPT})?\n"
        "Script này cần quyền sudo.",
        assume_yes,
    ):
        return False
    if not shutil.which("curl"):
        log("máy chưa có curl. Hãy cài curl rồi chạy lại.")
        return False
    step("Đang cài Ollama")
    result = subprocess.run(
        f"curl -fsSL {LINUX_INSTALL_SCRIPT} | sh", shell=True, check=False
    )
    return result.returncode == 0 and ollama_executable() is not None


def ensure_ollama(assume_yes: bool) -> Optional[str]:
    binary = ollama_executable()
    if binary:
        log(f"Ollama đã được cài: {binary}")
        return binary

    step("Chưa tìm thấy Ollama trên máy này")
    installed = (
        install_windows(assume_yes)
        if IS_WINDOWS
        else install_macos(assume_yes)
        if IS_MACOS
        else install_linux(assume_yes)
    )
    binary = ollama_executable()
    if not installed and not binary:
        return None
    return binary


def ensure_server(binary: str) -> bool:
    if ollama_running(OLLAMA_URL):
        log(f"Máy chủ Ollama đang chạy tại {OLLAMA_URL}")
        return True
    step("Đang khởi động máy chủ Ollama")
    start_ollama_server(binary)
    for _ in range(30):
        if ollama_running(OLLAMA_URL, timeout=1.0):
            log("đã sẵn sàng")
            return True
        time.sleep(1)
    log("máy chủ chưa phản hồi. Hãy mở ứng dụng Ollama rồi chạy lại script này.")
    return False


# ─────────────────────────────────────── pull model ────────────────────────────


def pull_model(binary: str, model: str) -> bool:
    step(f"Đang tải mô hình '{model}' (vài GB — có thể mất 10–30 phút)")
    log("Chỉ tải một lần. Lần sau chạy ứng dụng là dùng được ngay.")
    result = subprocess.run([binary, "pull", model], check=False)
    return result.returncode == 0


def model_present(binary: str, model: str) -> bool:
    try:
        listed = subprocess.run(
            [binary, "list"], capture_output=True, text=True, timeout=30
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    # `ollama list` prints "name:tag" -- a bare name means the :latest tag.
    wanted = model if ":" in model else f"{model}:latest"
    return wanted in listed


# ─────────────────────────────────────── main ──────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Cài LLM chạy hoàn toàn trên máy (Ollama) cho PDF Table Flattener."
    )
    parser.add_argument(
        "--model", default=DEFAULT_MODEL, help=f"Tên mô hình (mặc định: {DEFAULT_MODEL})"
    )
    parser.add_argument(
        "-y", "--yes", action="store_true", help="Đồng ý mọi bước, không hỏi lại"
    )
    args = parser.parse_args()

    print("=" * 68)
    print("  Cài LLM local cho PDF Table Flattener")
    print(f"  Hệ điều hành : {platform.system()} {platform.machine()}")
    print(f"  Mô hình      : {args.model}")
    print("  Mô hình chạy 100% trên máy bạn, không gửi tài liệu đi đâu cả.")
    print("=" * 68)

    binary = ensure_ollama(args.yes)
    if not binary:
        print(
            "\nChưa cài được Ollama. Ứng dụng vẫn dùng bình thường được — "
            "chỉ là không có phần tinh chỉnh bằng LLM."
        )
        return 1

    if not ensure_server(binary):
        return 1

    if model_present(binary, args.model):
        log(f"Mô hình '{args.model}' đã có sẵn.")
    elif not pull_model(binary, args.model):
        print(f"\nKhông tải được mô hình '{args.model}'. Hãy thử lại sau.")
        return 1

    print("\n" + "=" * 68)
    print("  XONG! Mở lại ứng dụng và tick vào ô 'Dùng LLM local (Ollama)'.")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nĐã huỷ.")
        sys.exit(130)
