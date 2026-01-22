#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

APP_NAME="Sentry"
ENTRY="run.py"

rm -rf venv build dist

python3 -m venv venv
source venv/bin/activate

python -m pip install -U pip
pip install -r requirements.txt

PKGS=$(pip freeze | cut -d'=' -f1)

pip install pip-licenses
pip-licenses --with-urls --with-license-file --with-notice-file --format=plain-vertical --packages $PKGS --output-file THIRD_PARTY_NOTICES.raw.txt

sed -E '/^\//d' THIRD_PARTY_NOTICES.raw.txt > THIRD_PARTY_NOTICES.txt
rm -f THIRD_PARTY_NOTICES.raw.txt

pip install pip-audit
if ! pip-audit -r requirements.txt; then
    echo "WARNING: Security vulnerabilities found!"
    read -p "Press Enter to continue building anyway..."
fi

pip install pyinstaller
pyinstaller --clean --noconfirm --onefile --name "$APP_NAME" "$ENTRY"

cp -f THIRD_PARTY_NOTICES.txt "dist/THIRD_PARTY_NOTICES.txt"
