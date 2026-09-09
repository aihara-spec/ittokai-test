@echo off
cd /d "%~dp0"
title ITTOKAI
python -m pip install -r requirements.txt >nul 2>&1
start "" http://localhost:8000
python server.py
pause
