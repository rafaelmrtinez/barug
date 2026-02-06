@echo off
title BaRUG Django Server

REM ==============================
REM CONFIG: PROJECT ROOT
REM ==============================
REM This MUST be the folder where:
REM - manage.py exists
REM - you run git pull
REM - venv folder exists

set PROJECT_ROOT=C:\Users\panch\OneDrive\BaRUG v3 Jan 31\barug-for_lupon_updated

REM ==============================
REM GO TO PROJECT ROOT
REM ==============================
cd /d "%PROJECT_ROOT%"

echo.
echo ==============================
echo Running Django from:
echo %CD%
echo ==============================
echo.

REM ==============================
REM ACTIVATE VIRTUAL ENV
REM ==============================
call venv\Scripts\activate.bat

REM ==============================
REM SHOW CURRENT GIT COMMIT
REM ==============================
echo Current Git Commit:
git rev-parse --short HEAD
echo.

REM ==============================
REM GET ACTIVE IPV4 ADDRESS
REM ==============================
for /f %%i in ('powershell -Command "(Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.PrefixOrigin -eq 'Dhcp' -and $_.IPAddress -notlike '169.*'}).IPAddress"') do set MYIP=%%i

echo Using IP: %MYIP%
echo.

REM ==============================
REM START DJANGO SERVER (NEW WINDOW)
REM ==============================
start "BaRUG Django Server" cmd /k python manage.py runserver 0.0.0.0:8005

REM ==============================
REM WAIT FOR SERVER
REM ==============================
timeout /t 3 /nobreak >nul

REM ==============================
REM OPEN BROWSER
REM ==============================
start "" http://%MYIP%:8005/

pause
