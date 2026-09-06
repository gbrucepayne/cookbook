import os

from flask import Flask
from flask_migrate import Migrate
from flask_wtf import CSRFProtect

from config import Config

from .models import db

csrf = CSRFProtect()

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize extensions
    db.init_app(app)
    csrf.init_app(app)
    
    migrate = Migrate(app, db, render_as_batch=True)
    
    os.makedirs(app.config['IMAGE_FOLDER'], exist_ok=True)

    # Register blueprints (routes)
    from app.routes.recipe_routes import recipe_bp
    app.register_blueprint(recipe_bp)

    return app
