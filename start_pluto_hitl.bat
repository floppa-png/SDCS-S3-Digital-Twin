@echo off
title SDCS Digital Twin - Pluto SDR HITL Mode
echo ============================================================
echo   SDCS Digital Twin - Pluto SDR Hardware-In-The-Loop (HITL)
echo ============================================================
echo.
cd /d "%~dp0"
call python_ml\venv\Scripts\python.exe run_project.py --hitl
pause
