@echo off
title SDCS Digital Twin - Simulation Mode
echo ============================================================
echo   SDCS Digital Twin - Simulation Mode (Pure Software)
echo ============================================================
echo.
cd /d "%~dp0"
call python_ml\venv\Scripts\python.exe run_project.py
pause
