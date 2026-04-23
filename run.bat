@echo off
REM Double-click to launch Through the Wall (Windows dev mode).
cd /d "%~dp0"
start "" .venv\Scripts\pythonw.exe app.py
