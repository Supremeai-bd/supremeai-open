@echo off
title SupremeAI: Multi-AI Fleet SSO Authenticator
cd /d "%~dp0"
cls

:MENU
echo =======================================================================
echo          SupremeAI: Autonomous Multi-AI Fleet SSO Authenticator
echo =======================================================================
echo   Please select which AI platform you want to authenticate:
echo.
echo   [1] ChatGPT          (chatgpt.com)       - GPT-4o / 4o-mini
echo   [2] Mistral Le Chat  (chat.mistral.ai)   - Mistral Large 2 / Codestral
echo   [3] Perplexity AI    (perplexity.ai)     - Live Web Search AI
echo   [4] Grok             (grok.com)          - x.ai Grok Fleet
echo   [5] Gemini Web       (gemini.google.com) - Gemini 2.0 / 1.5 Pro
echo   [6] Authenticate ALL (Sequential Auto-Run)
echo   [0] Open Sovereign Browser Profile (Direct 1-Click Manual Navigation)
echo   [7] Exit
echo =======================================================================
set /p choice="Enter your choice (0-7): "

if "%choice%"=="0" goto MANUAL
if "%choice%"=="1" goto CHATGPT
if "%choice%"=="2" goto MISTRAL
if "%choice%"=="3" goto PERPLEXITY
if "%choice%"=="4" goto GROK
if "%choice%"=="5" goto GEMINI
if "%choice%"=="6" goto ALL
if "%choice%"=="7" goto EXIT

echo Invalid choice! Please select 0 to 7.
timeout /t 2 >nul
cls
goto MENU

:MANUAL
echo.
echo [*] Opening Sovereign Profile in Microsoft Edge...
python launch_manual_login.py
pause
cls
goto MENU

:CHATGPT
echo.
echo [*] Initiating ChatGPT Authentication...
python multi_ai_sso_runner.py chatgpt
pause
cls
goto MENU

:MISTRAL
echo.
echo [*] Initiating Mistral Le Chat Authentication...
python multi_ai_sso_runner.py mistral
pause
cls
goto MENU

:PERPLEXITY
echo.
echo [*] Initiating Perplexity AI Authentication...
python multi_ai_sso_runner.py perplexity
pause
cls
goto MENU

:GROK
echo.
echo [*] Opening Grok in Sovereign Profile...
python launch_manual_login.py https://grok.com
pause
cls
goto MENU

:GEMINI
echo.
echo [*] Initiating Gemini Web Authentication...
python multi_ai_sso_runner.py gemini
pause
cls
goto MENU

:ALL
echo.
echo [*] Initiating Full Fleet Authentication...
python multi_ai_sso_runner.py all
pause
cls
goto MENU

:EXIT
echo Exiting...
exit /b 0
