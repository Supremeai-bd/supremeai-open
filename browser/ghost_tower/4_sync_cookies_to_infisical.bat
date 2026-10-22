@echo off
title SupremeAI: Sync AI Fleet Cookies to Infisical Cloud Vault
echo ======================================================================
echo   SupremeAI: AI Fleet Cookies Exporter & Infisical Cloud Sync ($0)
echo ======================================================================
echo.
cd /d "%~dp0"
python sync_cookies_to_infisical.py
echo.
echo ======================================================================
echo Sync completed! Local PC can now be closed.
echo All cloud services (Render / Cloudflare) will run 24/7 with these sessions.
echo ======================================================================
echo.
pause
