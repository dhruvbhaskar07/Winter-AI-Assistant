#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
PY_EXE=".venv/bin/python"

ensure_venv() {
  if [ -x "$PY_EXE" ]; then
    echo "[OK] .venv ready."
    return 0
  fi

  echo "[INFO] Creating .venv virtual environment..."
  if ! command -v python3 >/dev/null 2>&1; then
    echo "[ERR] python3 not found. Install Python 3.10+ first."
    return 1
  fi

  python3 -m venv .venv

  if [ ! -x "$PY_EXE" ]; then
    echo "[ERR] Failed to create .venv"
    return 1
  fi

  echo "[OK] .venv ready."
}

pip_upgrade_core() {
  echo "[INFO] Upgrading pip..."
  "$PY_EXE" -m pip install --upgrade pip
  echo "[OK] pip updated."
}

install_req_core() {
  echo "[INFO] Installing requirements..."
  "$PY_EXE" -m pip install -r requirements.txt
  echo "[OK] Requirements installed."
}

make_env_core() {
  if [ -f ".env" ]; then
    echo "[OK] .env already exists."
    return 0
  fi

  if [ ! -f ".env.example" ]; then
    echo "[ERR] .env.example not found."
    return 1
  fi

  cp .env.example .env
  echo "[WARN] .env created. Please set API_KEY before run."
}

run_ui() {
  ensure_venv || return 1
  if [ ! -f ".env" ]; then
    echo "[ERR] .env missing. Use option 5 first."
    return 1
  fi
  echo "[INFO] Starting UI..."
  "$PY_EXE" ui.py
}

run_cli() {
  ensure_venv || return 1
  if [ ! -f ".env" ]; then
    echo "[ERR] .env missing. Use option 5 first."
    return 1
  fi
  echo "[INFO] Starting CLI/Voice mode..."
  "$PY_EXE" main.py
}

health_check() {
  ensure_venv || return 1
  echo "[INFO] Running quick health check..."
  "$PY_EXE" -c "import main, ui; print('OK: import check passed')"
  echo "[OK] Health check passed."
}

pause_prompt() {
  read -r -p "Press Enter to continue..." _
}

while true; do
  clear
  echo "=========================================="
  echo "  Winter AI Linux - Easy 9 Options"
  echo "=========================================="
  echo "1. First Time Full Setup"
  echo "2. Create/Repair Virtual Environment"
  echo "3. Upgrade pip"
  echo "4. Install/Update Requirements"
  echo "5. Create .env from .env.example"
  echo "6. Run Desktop UI"
  echo "7. Run Voice/CLI Mode"
  echo "8. Quick Health Check"
  echo "9. Exit"
  echo "=========================================="
  read -r -p "Choose option (1-9): " choice

  case "$choice" in
    1)
      echo "[INFO] Running first-time full setup..."
      ensure_venv && pip_upgrade_core && install_req_core && make_env_core
      pause_prompt
      ;;
    2)
      ensure_venv
      pause_prompt
      ;;
    3)
      ensure_venv && pip_upgrade_core
      pause_prompt
      ;;
    4)
      ensure_venv && install_req_core
      pause_prompt
      ;;
    5)
      make_env_core
      pause_prompt
      ;;
    6)
      run_ui
      pause_prompt
      ;;
    7)
      run_cli
      pause_prompt
      ;;
    8)
      health_check
      pause_prompt
      ;;
    9)
      echo "[INFO] Exit."
      exit 0
      ;;
    *)
      echo "[WARN] Invalid option. Please select 1-9."
      pause_prompt
      ;;
  esac
done
