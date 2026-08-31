@echo off
rem ===================================================================
rem  PDF Table Flattener - Windows launcher
rem  Double-click this file to run the app.
rem  The first run installs everything (needs Internet); later runs go
rem  straight to the application.
rem ===================================================================
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title PDF Table Flattener
rem UTF-8 console, else non-ASCII document names come out as mojibake
chcp 65001 >nul 2>&1
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

rem --- Already installed: run straight away, no system Python needed --
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" "tools\bootstrap.py" --mode gui
    if !errorlevel! equ 0 goto :eof
    echo.
    echo The existing environment looks broken. Reinstalling...
    echo.
)

rem --- Find a Python 3.10+ that has tkinter --------------------------
set "PYEXE="
for %%C in ("py -3" "python" "python3") do (
    if not defined PYEXE (
        %%~C -c "import sys,tkinter;raise SystemExit(0 if sys.version_info>=(3,10) else 1)" >nul 2>&1
        if !errorlevel! equ 0 set "PYEXE=%%~C"
    )
)

if defined PYEXE goto :RUN

rem --- No Python: fetch a private one just for this app --------------
echo.
echo ===================================================================
echo   No suitable Python found. Downloading a private copy for this app.
echo   This runs ONCE and needs an Internet connection.
echo ===================================================================
echo.

set "UV=%USERPROFILE%\.local\bin\uv.exe"
if not exist "%UV%" (
    echo [1/2] Downloading the installer...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
)
if not exist "%UV%" (
    echo.
    echo ERROR: the automatic installer could not be downloaded.
    echo Install Python manually from https://www.python.org/downloads/
    echo  - tick "Add python.exe to PATH" during setup
    echo  - then run this file again
    echo.
    pause
    exit /b 1
)

echo [2/2] Installing Python 3.12...
"%UV%" python install 3.12
for /f "usebackq delims=" %%P in (`"%UV%" python find 3.12 2^>nul`) do set "PYEXE=%%P"

if not defined PYEXE (
    echo.
    echo ERROR: Python could not be installed automatically.
    echo Install it manually from https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

:RUN
%PYEXE% "tools\bootstrap.py" --mode gui
if !errorlevel! neq 0 (
    echo.
    echo The application exited with an error. See the message above.
    echo.
    pause
    exit /b 1
)
