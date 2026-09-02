"""One-time database initialization script when deploying.

De-conflicts WGSI servers that launch multiple workers.
"""

from app import db
from run import app

with app.app_context():
    db.create_all()
