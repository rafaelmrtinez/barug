@echo off
title BaRUG Django Server

cd /d "C:\Users\panch\OneDrive\BaRUG v3 Jan 31\barug-for_lupon_updated\barug-for_lupon"

:: Get active IPv4 using PowerShell
for /f %%i in ('powershell -Command "(Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias Wi-Fi | Where-Object {$_.PrefixOrigin -eq 'Dhcp'}).IPAddress"') do set MYIP=%%i

:: Run Django server in a new window
start "" venv\Scripts\python.exe manage.py runserver 0.0.0.0:8005

:: Wait a bit to let Django start (optional, but avoids blank page)
timeout /t 3 /nobreak >nul

:: Open browser to current IP
start "" http://%MYIP%:8005/

pause
