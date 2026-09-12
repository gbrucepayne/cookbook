"""Database models and helpers.
"""
import json
from enum import Enum
from typing import Any

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, inspect, or_, select
from sqlalchemy.types import Enum as SqlEnum
from sqlalchemy.types import Integer as SqlInteger
from sqlalchemy.types import String as SqlString
from sqlalchemy.types import Text as SqlText

db = SQLAlchemy()


class LoggableModelMixin:
    """Provides automatic dictionary serialization for SQLAlchemy models."""
    
    def to_dict(self) -> dict:
        inst = inspect(self)
        # Safely extract column attributes, bypassing SQLAlchemy's internal state
        fields = {c.key: getattr(self, c.key) for c in inst.mapper.column_attrs}
        
        # Optional: Include loaded relationships if you want to see them in logs
        for rel in inst.mapper.relationships:
            # Only dump if the relationship is already loaded to avoid lazy-query pollution
            if rel.key in inst.dict:
                related_obj = getattr(self, rel.key)
                if related_obj is None:
                    fields[rel.key] = None
                elif isinstance(related_obj, list):
                    fields[rel.key] = [
                        {c.key: getattr(item, c.key) for c in inspect(item).mapper.column_attrs}
                        for item in related_obj
                    ]
                else:
                    fields[rel.key] = {
                        c.key: getattr(related_obj, c.key) for c in inspect(related_obj).mapper.column_attrs
                    }
                    
        return fields

    def to_json_str(self, indent: int = 2) -> str:
        """Returns a cleanly formatted JSON string representation of the model."""
        return json.dumps(self.to_dict(), indent=indent, default=str)


class RecipeCategory(Enum):
    MAIN = 'MAIN'
    SIDE = 'SIDE'
    COMPANION = 'COMPANION'
    DESSERT = 'DESSERT'
    STARTER = 'STARTER'


# Association table for companion recipes
recipe_companions = db.Table(
    'recipe_companions',
    db.Column(
        'recipe_id',
        db.Integer,
        db.ForeignKey('recipes.id', ondelete='CASCADE'),
        primary_key=True,
    ),
    db.Column(
        'companion_id',
        db.Integer,
        db.ForeignKey('recipes.id', ondelete='CASCADE'),
        primary_key=True,
    ),
)


class Recipe(LoggableModelMixin, db.Model):
    __tablename__ = 'recipes'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    source_url = db.Column(db.String(500), nullable=True)
    
    category = db.Column(
        db.Enum(RecipeCategory, native_enum=False),
        nullable = False,
        default = RecipeCategory.MAIN,
    )
    
    ingredients = db.Column(db.Text, nullable=False)
    instructions = db.Column(db.Text, nullable=False)
    image_url = db.Column(db.String(500), nullable=True)
    
    servings = db.Column(db.Integer, nullable=True)
    prep_time = db.Column(db.Integer, nullable=True)
    cook_time = db.Column(db.Integer, nullable=True)
    total_time = db.Column(db.Integer, nullable=True)
    
    description = db.Column(db.Text, nullable=True)
    rating = db.Column(db.Integer, nullable=False, default=0)
    notes = db.Column(db.Text, nullable=True)
    
    companions = db.relationship(
        'Recipe',
        secondary=recipe_companions,
        primaryjoin=(recipe_companions.c.recipe_id == id),
        secondaryjoin=(recipe_companions.c.companion_id == id),
        backref=db.backref('paired_with', lazy='dynamic'),
        lazy='dynamic',
    )


def recipe_exists(title: str, source: str = '') -> bool:
    """Check if the title exists in the recipes table."""
    if not source:
        query = select(Recipe).where(Recipe.title == title)
    else:
        query = select(Recipe).where(or_ (
            func.lower(Recipe.title) == title.lower(),
            func.lower(Recipe.source_url) == source.lower(),
        ))
    result = db.session.scalar(query)
    return result is not None


def valid_fields() -> tuple[str]:
    """Get the valid Recipe columns."""
    mapper = inspect(Recipe)
    return { attr.key for attr in mapper.columns }


def required_fields() -> set[str]:
    """Get the required Recipe columns."""
    required = set()
    mapper = inspect(Recipe)
    for col in mapper.columns:
        if (
            not col.nullable and
            col.default is None and
            col.server_default is None and
            not col.primary_key
        ):
            required.add(col.name)
    return required


def field_type(field_name: str) -> Any:
    """Get the column type."""
    mapper = inspect(Recipe)
    column_types = {col.name: col.type for col in mapper.columns}
    column_type = column_types.get(field_name)
    if isinstance(column_type, SqlEnum):
        return column_type.enum_class
    if isinstance(column_type, SqlInteger):
        return int
    if isinstance(column_type, (SqlString, SqlText)):
        return str
    return None
