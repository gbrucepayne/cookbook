# gunicorn.conf.py

import os

from dotenv import load_dotenv

load_dotenv()

port = os.getenv('PORT', '5001')
bind = f"0.0.0.0:{port}"
workers = 3
timeout = 60
