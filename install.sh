#!/bin/bash

set -e

TAG="[COOKBOOK INSTALLER]"

export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"

if [ ! -x "$PYENV_ROOT/bin/pyenv" ]; then
  echo "$TAG ERROR: pyenv not found at $PYENV_ROOT/bin/pyenv"
  exit 1
fi

eval "$("$PYENV_ROOT/bin/pyenv" init -)"

if ! command -v pyenv >/dev/null 2>&1; then
  echo "$TAG ERROR: pyenv initialization failed"
fi

if ! pyenv versions --bare | grep -q '^3\.10\.'; then
  echo "$TAG Please use pyenv to install python 3.10"
  exit 1
fi

if [ "$PWD" != "/opt/cookbook" ]; then
  echo "$TAG ERROR: script must be run from /opt/cookbook"
  echo "$TAG Current directory: $PWD"
  exit 1
fi

pyenv local 3.10
PYTHON_VERSION=$(python -V)
echo "$TAG Creating virtual environment with Python $PYTHON_VERSION..."
python -m venv .venv
source .venv/bin/activate
echo "$TAG Upgrading pip..."
pip install --upgrade pip
echo "$TAG Installing Python dependencies..."
pip install -r requirements.txt

echo "$TAG Initializing database..."
export FLASK_APP=run.py
flask db upgrade

deactivate

if ! grep -q "PORT=8081" .env 2>/dev/null; then
  echo PORT=8081 >> .env
fi

echo "$TAG Setting up systemd cookbook.service..."
sudo cp cookbook.service /etc/systemd/system
sudo sed -i "s/^User=cookbook$/User=$USER/" /etc/systemd/system/cookbook.service
sudo sed -i "s/^Group=cookbook$/Group=$USER/" /etc/systemd/system/cookbook.service

sudo systemctl enable cookbook.service
sudo systemctl start cookbook.service

echo "$TAG Installation complete."