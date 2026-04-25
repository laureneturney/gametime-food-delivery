#!/usr/bin/env bash
# One-shot launcher for the GameTime Food Delivery demo.
# Creates a venv on first run, installs deps, and starts Streamlit.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

VENV_DIR="$PROJECT_DIR/venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "==> Creating virtual environment at $VENV_DIR"
    python3 -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

echo "==> Installing core dependencies"
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

# Only install the IBM watsonx SDK if the user actually selected it.
# (It pulls in pandas/numpy and may fail on bleeding-edge Python versions.)
if [ -f .env ] && grep -qE '^[[:space:]]*LLM_PROVIDER[[:space:]]*=[[:space:]]*watsonx' .env; then
    echo "==> LLM_PROVIDER=watsonx detected — installing IBM watsonx SDK"
    pip install -r requirements-watsonx.txt
fi

if [ ! -f .env ]; then
    echo "==> Creating .env from .env.example"
    cp .env.example .env
fi

echo "==> Launching Streamlit at http://localhost:8501"
exec streamlit run frontend/app.py
