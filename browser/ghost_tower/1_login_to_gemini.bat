@echo off
title SupremeAI: Google Gemini Login Helper
echo ======================================================================
echo   SupremeAI: Google Gemini One-Time Account Login
echo ======================================================================
echo.
cd /d "%~dp0"
python login_helper.py
echo.
echo Setup finished! You can now run start_gemini_web_chat.bat
pause
