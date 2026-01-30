#!/bin/bash
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR"

if [ ! -d "venv" ]; then
    echo "First time setup: Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate

echo "Checking dependencies..."
pip install -q -r requirements.txt

echo "Starting Sentry..."
python3 -X faulthandler run.py
