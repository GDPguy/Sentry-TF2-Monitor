@echo off
setlocal enabledelayedexpansion

set APP_NAME=Sentry
set ENTRY=run.py

if exist venv rd /s /q venv
if exist build rd /s /q build
if exist dist rd /s /q dist

py -3.13 -m venv venv
call venv\Scripts\activate.bat

python -m pip install -U pip
pip install -r requirements.txt

set "PKGS="
for /f "delims==" %%a in ('pip freeze') do (
    set "PKGS=!PKGS! %%a"
)

pip install pip-licenses
pip-licenses --with-urls --with-license-file --with-notice-file --format=plain-vertical --packages %PKGS% --output-file THIRD_PARTY_NOTICES.raw.txt

findstr /V /R "^[a-zA-Z]:" THIRD_PARTY_NOTICES.raw.txt > THIRD_PARTY_NOTICES.txt
del THIRD_PARTY_NOTICES.raw.txt

pip install pip-audit
pip-audit -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo WARNING: Security vulnerabilities found!
    pause
)

pip install pyinstaller
pyinstaller --clean --noconfirm --onefile --noconsole --name "%APP_NAME%" "%ENTRY%"

copy /Y THIRD_PARTY_NOTICES.txt dist\%APP_NAME%_THIRD_PARTY_NOTICES.txt >nul
endlocal
