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
PYTHON_VERSION=$(python -V)
echo "Creating virtual environment with Python $PYTHON_VERSION..."
python -m venv .venv
source .venv/bin/activate
echo "Upgrading pip..."
pip install --upgrade pip
echo "Installing dependencies..."
pip install -r requirements.txt
echo "Initializing database..."
python init_db.py
deactivate
echo PORT=8081 >> .env
echo "Setting up systemd cookbook.service..."
sudo cp cookbook.service /etc/systemd/system
sudo sed -i "s/^User=cookbook$/User=$USER/" /etc/systemd/system/cookbook.service
sudo sed -i "s/^Group=cookbook$/Group=$USER/" /etc/systemd/system/cookbook.service

sudo systemctl enable cookbook.service
sudo systemctl start cookbook.service

echo "Cookbook installation complete."