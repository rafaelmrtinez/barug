@echo off
echo Downloading Bootstrap 5.3.0 files...

:: Create directories
mkdir "static\bootstrap\css" 2>nul
mkdir "static\bootstrap\js" 2>nul

:: Download Bootstrap CSS
echo Downloading Bootstrap CSS...
curl -L "https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" -o "static\bootstrap\css\bootstrap.min.css"

:: Download Bootstrap JS Bundle (includes Popper)
echo Downloading Bootstrap JS...
curl -L "https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js" -o "static\bootstrap\js\bootstrap.bundle.min.js"

echo.
echo Bootstrap files downloaded successfully!
echo Files saved to:
echo - static\bootstrap\css\bootstrap.min.css
echo - static\bootstrap\js\bootstrap.bundle.min.js
echo.
echo Next step: Update base.html to use these local files
pause
