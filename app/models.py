import json
from enum import Enum

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, or_, select, inspect

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
