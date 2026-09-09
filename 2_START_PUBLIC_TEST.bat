@echo off
cd /d "%~dp0"
title ITTOKAI Public Test
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0public_test.ps1"
pause
