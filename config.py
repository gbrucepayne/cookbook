import os
from typing import ClassVar

from dotenv import load_dotenv

load_dotenv()


class Config:
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.path.join(BASE_DIR, 'recipes.db')}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = os.environ.get('COOKBOOK_KEY', 'devkey')
    IMAGE_FOLDER = os.path.join(BASE_DIR, 'app', 'static', 'images')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    ALLOWED_EXTENSIONS: ClassVar[set[str]] = {'png', 'jpg', 'jpeg', 'webp', 'gif', 'heic', 'heif'}
