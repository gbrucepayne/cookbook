#!/bin/bash

set -e

export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"

if [ ! -x "$PYENV_ROOT/bin/pyenv" ]; then
  echo "ERROR: pyenv not found at $PYENV_ROOT/bin/pyenv"
  exit 1
fi

eval "$("$PYENV_ROOT/bin/pyenv" init -)"

if ! command -v pyenv >/dev/null 2>&1; then
  echo "ERROR: pyenv initialization failed"
fi

if ! pyenv versions --bare | grep -q '^3\.10\.'; then
  echo "Please use pyenv to install python 3.10"
  exit 1
fi

if [ "$PWD" != "/opt/cookbook" ]; then
  echo "ERROR: script must be run from /opt/cookbook"
  echo "Current directory: $PWD"
  exit 1
fi

pyenv local 3.10
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
python init_db.py
deactivate
echo PORT=8081 >> .env
sudo cp cookbook.service /etc/systemd/system

if ! id cookbook >/dev/null 2>&1; then
  sudo useradd --system --home /opt/cookbook --shell /usr/sbin/nologin cookbook
fi
sudo chown -R cookbook:cookbook /opt/cookbook

echo "Cookbook installation complete."