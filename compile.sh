#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

APP_NAME="Sentry"
ENTRY="run.py"

echo "[1/7] Cleaning previous builds..."
rm -rf venv build dist

echo "[2/7] Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

echo "[3/7] Installing application dependencies..."
python -m pip install -U pip
pip install -r requirements.txt

echo "[4/7] Generating THIRD_PARTY_NOTICES.txt..."
pip install pip-licenses

pip-licenses \
    --with-urls \
    --with-license-file \
    --with-notice-file \
    --format=plain-vertical \
    --ignore-packages pip-licenses prettytable wcwidth pip setuptools wheel \
    --output-file THIRD_PARTY_NOTICES.raw.txt

sed -E '/^\//d' THIRD_PARTY_NOTICES.raw.txt > THIRD_PARTY_NOTICES.txt
rm -f THIRD_PARTY_NOTICES.raw.txt

echo "[5/7] Running Security Audit..."
pip install pip-audit
if ! pip-audit -r requirements.txt; then
    echo "WARNING: Security vulnerabilities found!"
    read -p "Press Enter to continue building anyway..."
fi

echo "[6/7] Building with PyInstaller..."
pip install pyinstaller
pyinstaller --clean --noconfirm --onefile --name "$APP_NAME" "$ENTRY"

echo "[7/7] Finalizing..."
cp -f THIRD_PARTY_NOTICES.txt "dist/THIRD_PARTY_NOTICES.txt"

echo ""
echo "Build Complete. Binary is in the 'dist' folder."
