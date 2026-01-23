@echo off
setlocal enabledelayedexpansion

set APP_NAME=Sentry
set ENTRY=run.py

echo [1/7] Cleaning previous builds...
if exist venv rd /s /q venv
if exist build rd /s /q build
if exist dist rd /s /q dist

echo [2/7] Creating virtual environment...
python -m venv venv
call venv\Scripts\activate.bat

echo [3/7] Installing application dependencies...
python -m pip install -U pip
pip install -r requirements.txt

echo [4/7] Generating THIRD_PARTY_NOTICES.txt...

pip install pip-licenses

pip-licenses ^
    --with-urls ^
    --with-license-file ^
    --with-notice-file ^
    --format=plain-vertical ^
    --ignore-packages pip-licenses prettytable wcwidth pip setuptools wheel ^
    --output-file THIRD_PARTY_NOTICES.raw.txt

findstr /V /R "^[a-zA-Z]:" THIRD_PARTY_NOTICES.raw.txt > THIRD_PARTY_NOTICES.txt
del THIRD_PARTY_NOTICES.raw.txt

echo [5/7] Running Security Audit...
pip install pip-audit

pip-audit -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo WARNING: Security vulnerabilities found!
    pause
)

echo [6/7] Building EXE with PyInstaller...
pip install pyinstaller
pyinstaller --clean --noconfirm --onefile --noconsole --name "%APP_NAME%" "%ENTRY%"

echo [7/7] Finalizing...
copy /Y THIRD_PARTY_NOTICES.txt dist\THIRD_PARTY_NOTICES.txt >nul

echo.
echo Build Complete. Binary is in the 'dist' folder.
pause
endlocal
