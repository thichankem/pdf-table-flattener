@echo off
rem ===================================================================
rem  PDF Table Flattener - Windows launcher
rem  Nhap doi chuot vao file nay de chay ung dung.
rem  Lan dau se tu cai dat (can Internet); cac lan sau mo thang ung dung.
rem ===================================================================
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title PDF Table Flattener
rem UTF-8 console, else the Vietnamese progress messages come out as mojibake
chcp 65001 >nul 2>&1
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

rem --- Da cai dat roi thi mo thang, khong can tim Python he thong -----
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" "tools\bootstrap.py" --mode gui
    if !errorlevel! equ 0 goto :eof
    echo.
    echo Moi truong cu co van de, dang cai dat lai...
    echo.
)

rem --- Tim mot ban Python 3.10+ co san tkinter ------------------------
set "PYEXE="
for %%C in ("py -3" "python" "python3") do (
    if not defined PYEXE (
        %%~C -c "import sys,tkinter;raise SystemExit(0 if sys.version_info>=(3,10) else 1)" >nul 2>&1
        if !errorlevel! equ 0 set "PYEXE=%%~C"
    )
)

if defined PYEXE goto :RUN

rem --- Khong co Python: tai ban Python rieng cho ung dung -------------
echo.
echo ===================================================================
echo   May nay chua co Python. Dang tai ve mot ban rieng cho ung dung.
echo   Buoc nay chi chay MOT lan va can ket noi Internet.
echo ===================================================================
echo.

set "UV=%USERPROFILE%\.local\bin\uv.exe"
if not exist "%UV%" (
    echo [1/2] Dang tai bo cai dat...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
)
if not exist "%UV%" (
    echo.
    echo LOI: khong tai duoc bo cai dat tu dong.
    echo Hay cai Python thu cong tai https://www.python.org/downloads/
    echo  - Nho tick "Add python.exe to PATH" khi cai
    echo  - Cai xong thi chay lai file nay
    echo.
    pause
    exit /b 1
)

echo [2/2] Dang cai Python 3.12...
"%UV%" python install 3.12
for /f "usebackq delims=" %%P in (`"%UV%" python find 3.12 2^>nul`) do set "PYEXE=%%P"

if not defined PYEXE (
    echo.
    echo LOI: khong cai duoc Python tu dong.
    echo Hay cai Python thu cong tai https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

:RUN
%PYEXE% "tools\bootstrap.py" --mode gui
if !errorlevel! neq 0 (
    echo.
    echo Ung dung ket thuc voi loi. Doc thong bao ben tren de biet nguyen nhan.
    echo.
    pause
    exit /b 1
)
