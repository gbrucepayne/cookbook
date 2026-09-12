import logging
import os
import re
from urllib.parse import urlparse

from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from app import db
from app.gemini import extract_recipe_genai
from app.image import download_and_cache_image, handle_image_upload
from app.ingredient import scale_ingredient_line
from app.models import (
    Recipe,
    RecipeCategory,
    field_type,
    recipe_exists,
    required_fields,
    valid_fields,
)
from app.ocr import extract_recipe_ocr, get_bounding_boxes
from app.scraper import scrape_recipe_from_url

logger = logging.getLogger(__name__)

recipe_bp = Blueprint('recipes', __name__)

MAIN_PAGE = 'recipes.html'

ICON = {
    'HOME': '',
    'MANUAL': '✍',
    'URL': '🔗',
    'SCAN': '📸',
    'SUCCESS': '🎉',
    'WARN': '⚠️',
    'FAIL': '❌' ,
}

OCR_DRAFTS = {}


def allowed_file(filename):
    return ('.' in filename and 
            filename.rsplit('.', 1)[1].lower() in 
            current_app.config['ALLOWED_EXTENSIONS'])


def image_folder():
    return current_app.config['IMAGE_FOLDER'] or './app/static/images'


@recipe_bp.route('/')
def index():
    """The Home page."""
    search_query = request.args.get('q', '').strip()
    selected_category = request.args.get('category', '').strip()
    
    per_page = request.args.get('per_page', 10, type=int)
    page = request.args.get('page', 1, type=int)
    
    query = Recipe.query
    
    if search_query:
        query = Recipe.query.filter(
            (Recipe.title.ilike(f'%{search_query}%')) | 
            (Recipe.ingredients.ilike(f'%{search_query}%')) |
            (Recipe.description.ilike(f'%{search_query}%'))
        )
    
    if selected_category:
        query = query.filter(Recipe.category == selected_category)
    
    query = query.order_by(Recipe.title.asc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    recipes = pagination.items
    
    return render_template(
        'recipes/home.html',
        recipes=recipes,
        categories=[category.name for category in RecipeCategory],
        pagination=pagination,
        search_query=search_query,
        selected_category=selected_category,
        per_page=per_page,
    )


@recipe_bp.route('/recipe/<int:recipe_id>')
def view_recipe(recipe_id):
    """Display the specified recipe."""
    recipe = Recipe.query.get_or_404(recipe_id)
    scale_factor = request.args.get('scale', 1.0, type=float)
    scaled_ingredients = [
        scale_ingredient_line(ing, scale_factor)
        for ing in recipe.ingredients.split('\n')
    ]
    recipe.ingredients = '\n'.join(scaled_ingredients)
    if isinstance(recipe.servings, int):
        recipe.servings = int(recipe.servings * scale_factor)
    all_recipes = Recipe.query.order_by(Recipe.title.asc()).all()
    return render_template(
        'recipes/view.html',
        recipe=recipe,
        current_scale=scale_factor,
        all_recipes=all_recipes,
    )


@recipe_bp.route('/recipe/create', methods=['POST'])
@recipe_bp.route('/recipe/<int:recipe_id>/edit', methods=['POST'])
def save_recipe(recipe_id=None):
    try:
        if recipe_id:
            recipe = Recipe.query.get_or_404(recipe_id)
        else:
            recipe = Recipe()
        
        for field, value in request.form.to_dict().items():
            if field not in valid_fields():
                logger.debug("Ignoring invalid field: %s", field)
                continue
            old_value = getattr(recipe, field)
            if field_type(field) is str:
                if isinstance(value, list):
                    value = '\n'.join([f"{item}".strip() for item in value])
                value = f"{value}".strip() or None
            elif field_type(field) is int:
                value = int(re.sub(r'\D', '', value) or 0) or None
            elif field_type(field) is RecipeCategory:
                value = RecipeCategory(value)
            if value != old_value:
                logger.debug("Updating %s", field)
                setattr(recipe, field, value)
                
        # Validate required fields
        for field in required_fields():
            value = getattr(recipe, field)
            if not value or len(value) == 0:
                raise ValueError(f"Invalid recipe {field}")
        
        if not recipe.total_time:
            recipe.total_time = sum([recipe.prep_time or 0,
                                     recipe.cook_time or 0]) or None
        
        if 'image_file' in request.files:
            file = request.files['image_file']
            if (file and file.filename != '' and allowed_file(file.filename)):
                filename = handle_image_upload(file,
                                               target_folder=image_folder(),
                                               suffix="manual")
                # Remove any old/temporary source file 
                # and point to the downloaded local/named image
                if filename:
                    if recipe.image_url:
                        try:
                            os.remove(os.path.join(image_folder(),
                                                   recipe.image_url))
                        except OSError:
                            pass
                recipe.image_url = filename

        # Fetch the list of submitted companion recipe ID strings
        # Returns an empty list [] if no options are highlighted
        selected_companion_ids = request.form.getlist('companions')

        # Convert string IDs to integer inputs safely
        selected_ids = [int(cid) for cid in selected_companion_ids 
                        if cid.isdigit()]

        # Pull the targeted matching recipe instances from the database
        new_companions: list[Recipe] = []
        if selected_ids:
            new_companions = Recipe.query.filter(
                Recipe.id.in_(selected_ids)).all()

        # If this is a brand-new recipe, add and flush it FIRST to generate ID
        # before linking companions
        if recipe_id is None:
            db.session.add(recipe)
            # Generate recipe.id in memory without committing yet
            db.session.flush()
            
        # Synchronize the relationship layer. Since it uses lazy='dynamic'
        # clear the association table array links and re-append
        recipe.companions = []
        for companion in new_companions:
            recipe.companions.append(companion)
            if recipe not in companion.companions.all():
                companion.companions.append(recipe)
        
        db.session.commit()
        logger.info("Updated recipe %s (id: %d)", recipe.title, recipe.id)
        flash(
            f"{ICON['SUCCESS']}"
            f" <b>{recipe.title}</b> was saved successfully!",
            "success"
        )
        return redirect(url_for('recipes.view_recipe', recipe_id=recipe.id))
    
    except Exception as e:
        flash(f"{ICON['FAIL']} {e}", "error")
        return redirect(url_for('recipes.index'))


@recipe_bp.route('/import_url', methods=['POST'])
def import_url():
    url = request.form.get('url')
    if url:
        parsed_url = urlparse(url)
        domain_name = parsed_url.netloc.lower().replace('www.', '')
        try:
            recipe = scrape_recipe_from_url(url)
            if not recipe or not recipe.title:
                raise ValueError('URL scraping failed')
            if recipe_exists(recipe.title, url):
                flash(
                    f"{ICON['FAIL']} Duplicate <b>{recipe.title}</b>.",
                    "error"
                )
            else:
                
                # Download and save the image locally
                if recipe.image_url:
                    recipe.image_url = download_and_cache_image(
                        external_img_url=recipe.image_url,
                        target_folder=image_folder(),
                        title=recipe.title,
                    )
                
                db.session.add(recipe)
                db.session.commit()
                logger.info("Imported %s from %s",
                            recipe.title, domain_name)
                flash(
                    f"{ICON['SUCCESS']} Successfully imported"
                    f" <b>{recipe.title}</b> from <i>{domain_name}</i>!",
                    "success"
                )
        except Exception as e:
            flash(
                f"{ICON['FAIL']} Failed to parse recipe"
                f" from the provided URL link: {e}",
                "error"
            )
    return redirect(url_for('recipes.index'))


@recipe_bp.route('/delete/<int:recipe_id>', methods=['POST'])
def delete_recipe(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    if recipe.image_url:
        try:
            os.remove(os.path.join(image_folder(), recipe.image_url))
        except OSError:
            pass
    db.session.delete(recipe)
    db.session.commit()
    logger.info("Deleted recipe: %s", recipe.title)
    return redirect(url_for('recipes.index'))


@recipe_bp.route('/scan_ocr', methods=['POST'])
def scan_ocr():
    """
    Accepts a single or multiple uploaded images of cookbook/magazine pages.
    Runs them through the multi-page OCR engine sequentially and returns 
    a structured JSON response to pre-populate the recipe creation form.
    """
    if 'image_files' not in request.files:
        return jsonify({"error": "No image files provided in request"}), 400
        
    uploaded_files = request.files.getlist('image_files')
    
    # Filter out empty form submissions
    valid_files = [f for f in uploaded_files if f and f.filename != '']
    if not valid_files:
        return jsonify({"error": "No files selected for scanning"}), 400

    saved_local_paths = []
    
    try:
        # Iterate and convert/save all incoming book pages safely
        for index, file_storage in enumerate(valid_files):
            if not allowed_file(file_storage.filename):
                continue
                
            # Get the clean filename string saved into IMAGE_FOLDER
            saved_filename = handle_image_upload(file_storage,
                                                 image_folder(),
                                                 suffix=f"scan_p{index+1}")
            
            if saved_filename:
                full_path = os.path.join(image_folder(), saved_filename)
                saved_local_paths.append(full_path)

        if not saved_local_paths:
            err_str = "No valid or allowed images could be processed"
            return jsonify({"error": err_str}), 400

        # First try GenAI extraction
        recipe = extract_recipe_genai(saved_local_paths, image_folder())
        if isinstance(recipe, Recipe):
            for attr in ['ingredients', 'instructions']:
                value = getattr(recipe, attr)
                if isinstance(value, list):
                    setattr(recipe, attr, '\n'.join(value))
        else:
            raise NotImplementedError("TODO: local OCR calibration/extraction")
            # Custom local OCR settings
            ocr_settings = {
                'k_width': request.form.get('k_width'),
                'k_height': request.form.get('k_height'),
                'y_tolerance': request.form.get('y_tolerance'),
            }
    
            recipe = extract_recipe_ocr(saved_local_paths,
                                        image_folder(),
                                        **ocr_settings)

        logger.debug("OCR returning: %s", recipe.to_dict())
        return render_template('recipes/modals/edit.html',
                               recipe=recipe,
                               form_id='ocr-recipe-form')
        
    except Exception as e:
        logger.error(f"Flask Multi-Page OCR Route failure: {e}")
        return (jsonify({"error": f"Internal server processing failure: {e}"}),
                500)
    
    finally:
        for file in saved_local_paths:
            os.remove(file)


@recipe_bp.route('/api/ocr/calculate-layout', methods=['POST'])
def calculate_ocr_layout():
    """
    Background API channel. Receives slider coordinates from the browser,
    runs localized OpenCV contour bounding logic, and returns real-time box data.
    """
    raise NotImplementedError("TODO: local OCR calibration interaction")
    data = request.get_json() or {}
    image_filename = data.pop('image_filename', None)
    if not image_filename:
        raise ValueError("Missing image filename")
    image_path = os.path.join(image_folder(), image_filename)
    result = get_bounding_boxes(image_path, **data)
    if not result:
        return jsonify({ "boxes": [], "rows_count": 0 }), 400
    return jsonify(result)
