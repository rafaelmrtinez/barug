@echo off
title BaRUG Django Server

:: Go to project root (where manage.py is)
cd /d "C:\Users\panch\OneDrive\BaRUG v3 Jan 31\barug-for_lupon_updated\barug-for_lupon"

:: Activate virtual environment
call venv\Scripts\activate.bat

:: Get active IPv4 using PowerShell
for /f %%i in ('powershell -Command "(Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.PrefixOrigin -eq 'Dhcp' -and $_.IPAddress -notlike '169.*'}).IPAddress"') do set MYIP=%%i

:: Run Django server in a new window USING THE VENV
start "BaRUG Django" cmd /k python manage.py runserver 0.0.0.0:8005

:: Wait a bit to let Django start
timeout /t 3 /nobreak >nul

:: Open browser to current IP
start "" http://%MYIP%:8005/

pause
