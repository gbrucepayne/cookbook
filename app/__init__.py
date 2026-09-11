import logging
import os

from flask import Flask
from flask_migrate import Migrate
from flask_wtf import CSRFProtect

from app.models import db
from config import Config

csrf = CSRFProtect()

DEBUG_LOG_MASK = ['httpcore', 'PIL', 'httpx', 'google']


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    root_logger = logging.getLogger()
    if 'gunicorn' in ''.join(logging.Logger.manager.loggerDict.keys()):
        gunicorn_logger = logging.getLogger('gunicorn.error')
        root_logger.handlers = gunicorn_logger.handlers
        root_logger.setLevel(gunicorn_logger.level)
        app.logger.handlers = gunicorn_logger.handlers
        app.logger.setLevel(gunicorn_logger.level)
        logging.getLogger('alembic').setLevel(logging.WARNING)
    else:
        if not root_logger.handlers:
            console_handler = logging.StreamHandler()
            dev_formatter = logging.Formatter(
                "[%(asctime)s] %(levelname)s (%(name)s): %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            )
            console_handler.setFormatter(dev_formatter)
            root_logger.addHandler(console_handler)
            root_logger.setLevel(logging.DEBUG)
            app.logger.setLevel(logging.DEBUG)
            for logger in DEBUG_LOG_MASK:
                logging.getLogger(logger).setLevel(logging.WARNING)

    # Initialize extensions
    db.init_app(app)
    csrf.init_app(app)
    
    _migrate = Migrate(app, db, render_as_batch=True)
    
    os.makedirs(app.config['IMAGE_FOLDER'], exist_ok=True)

    # Register blueprints (routes)
    from app.routes.recipe_routes import recipe_bp
    app.register_blueprint(recipe_bp)

    return app
