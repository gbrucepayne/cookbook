#!/bin/bash

set -e

source ~/.env

if [ -z "$GITHUB_TOKEN" ]; then
  echo "Please set GITHUB_TOKEN environment variable in the master .env file"
  exit 1
fi

if ! command -v pyenv >/dev/null 2>&1; then
  echo "Please install Pyenv and ensure it is in PATH"
  exit 1
fi

if ! pyenv versions --bare | grep -q '^3\.10\.'; then
  echo "Please use pyenv to install python 3.10"
  exit 1
fi

if [ -d /opt/cookbook ]; then
  echo "ERROR: /opt/cookbook already exists"
  exit 1
fi

# TODO: shift to Git credential or SSH deploy key
git clone https://${GITHUB_TOKEN}@github.com/gbrucepayne/cookbook.git /opt/cookbook
cd /opt/cookbook
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