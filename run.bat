@echo off
chcp 65001 > nul
title Word Table Converter Desktop App
cd /d "%~dp0"
"C:\Users\ADMIN\anaconda3\python.exe" -X utf8 gui_app.py
pause
