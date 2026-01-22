@echo off
cd /d "%~dp0"

if not exist "venv\" (
    echo First time setup: Creating virtual environment...
    python -m venv venv
)

call venv\Scripts\activate

echo Checking dependencies...
pip install -q -r requirements.txt

echo Starting Sentry...
python run.py

pause
