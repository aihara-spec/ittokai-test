@echo off
chcp 65001 > nul
cd /d %~dp0
python -m pip install -r requirements.txt
start "" http://localhost:8000
python server.py
pause
