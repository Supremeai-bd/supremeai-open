@echo off
title SupremeAI: AI Fleet Cookies & Health Check
echo ======================================================================
echo   SupremeAI: Local Cookies & Live Session Verifier
echo ======================================================================
echo.
cd /d "%~dp0"
python check_cookies_status.py
echo.
echo Check completed. Press any key to close this window.
pause >nul
