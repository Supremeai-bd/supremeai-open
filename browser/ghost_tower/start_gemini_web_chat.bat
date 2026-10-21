@echo off
title SupremeAI Ghost Tower — Live Gemini Web Chat ($0)
echo ======================================================================
echo   SupremeAI Ghost Tower: Live gemini.google.com Browser Relay ($0)
echo ======================================================================
echo.
echo [1/2] Launching Ghost Bridge Server on http://localhost:8788 ...
cd /d "%~dp0"
start "" "http://localhost:8788/"
python ghost_bridge_server.py
pause
