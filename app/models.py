from app import db


class Recipe(db.Model):
    __tablename__ = 'recipes'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    source_url = db.Column(db.String(500), nullable=True)
    ingredients = db.Column(db.Text, nullable=False)
    instructions = db.Column(db.Text, nullable=False)
    image_url = db.Column(db.String(500), nullable=True)
    servings = db.Column(db.Integer, nullable=True)
    prep_time = db.Column(db.Integer, nullable=True)
    cook_time = db.Column(db.Integer, nullable=True)
    description = db.Column(db.Text, nullable=True)
    rating = db.Column(db.Integer, nullable=False, default=0)
    notes = db.Column(db.Text, nullable=True)
