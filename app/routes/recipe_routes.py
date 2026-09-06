import os
import uuid
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
from app.image import download_and_cache_image, handle_image_upload
from app.ingredient import scale_ingredient_line
from app.models import Recipe, recipe_exists
from app.ocr import extract_text_from_pages, isolate_and_crop_embedded_image
from app.scraper import scrape_recipe_from_url

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


def get_image_folder():
    return current_app.config['IMAGE_FOLDER'] or './app/static/images'

# def handle_image_upload(file_storage, prefix="manual"):
#     """
#     Saves an uploaded file safely. If it's a HEIC file from an iPhone,
#     converts it to a web-friendly JPEG before writing to disk.
#     Returns the final saved filename string.
#     """
#     if not file_storage or file_storage.filename == '':
#         return None
        
#     filename = secure_filename(file_storage.filename)
#     base_name, ext = os.path.splitext(filename)
#     ext = ext.lower()
    
#     if ext in ['.heic', '.heif']:
#         # Generate target name pointing to progressive web-safe jpeg
#         target_filename = f"{prefix}_{base_name}.jpg"
#         full_dest_path = os.path.join(current_app.config['IMAGE_FOLDER'], target_filename)
        
#         try:
#             # Open HEIC file directly via pillow-heif plugin integration wrapper
#             heif_file = pillow_heif.read_heif(file_storage.stream)
#             image = Image.frombytes(
#                 heif_file.mode, 
#                 heif_file.size, 
#                 heif_file.data, 
#                 "raw", 
#                 heif_file.mode, 
#                 heif_file.stride,
#             )
#             # Save converted asset cleanly with high-grade compression matching web targets
#             image.save(full_dest_path, "JPEG", quality=85)
#             return target_filename
#         except Exception as e:
#             print(f"HEIC image conversion pipeline error: {e}")
#             return None
#     else:
#         # Standard web file type management (JPG, PNG, WebP)
#         target_filename = f"{prefix}_{filename}"
#         file_storage.save(os.path.join(current_app.config['IMAGE_FOLDER'], target_filename))
#         return target_filename


# def download_and_cache_image(external_img_url, title=""):
#     """
#     Downloads an external web image and writes it locally to the server upload folder.
#     Returns the newly created local filename string, or None if download fails.
#     """
#     if not external_img_url:
#         return None
#     try:
#         headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}
#         response = requests.get(external_img_url, headers=headers, timeout=10, stream=True)
#         response.raise_for_status()
        
#         # Deduce file extension from URL or fallback to jpeg
#         ext = '.jpg'
#         for allowed_ext in current_app.config['ALLOWED_EXTENSIONS']:
#             if f".{allowed_ext}" in external_img_url.lower():
#                 ext = f".{allowed_ext}"
#                 break
                
#         # Generate a collision-free filename asset token
#         random_hex = secrets.token_hex(8)
#         if title and not title.endswith("_"):
#             title = title.replace(' ', '_').replace('-', '_').lower() + '_'
#         local_filename = f"{title}scraped_{random_hex}{ext}"
#         full_dest_path = os.path.join(current_app.config['IMAGE_FOLDER'], local_filename)
            
        
#         # Stream the image file bits chunks safely onto server storage
#         with open(full_dest_path, 'wb') as f:
#             for chunk in response.iter_content(chunk_size=8192):
#                 f.write(chunk)
                
#         return local_filename
#     except Exception as e:
#         print(f"Failed to locally archive image asset: {e}")
#         return None


@recipe_bp.route('/')
def index():
    """The Home page."""
    search_query = request.args.get('q', '').strip()
    
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    if search_query:
        query = Recipe.query.filter(
            (Recipe.title.ilike(f'%{search_query}%')) | 
            (Recipe.ingredients.ilike(f'%{search_query}%')) |
            (Recipe.description.ilike(f'%{search_query}%'))
        )
    else:
        query = Recipe.query
    
    query = query.order_by(Recipe.title.asc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    recipes = pagination.items
    
    return render_template(
        'recipes/home.html',
        recipes=recipes,
        pagination=pagination,
        search_query=search_query,
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
    if recipe.servings:
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
        
        required_fields = ['title', 'ingredients', 'instructions']
        for field in required_fields:
            value = request.form.get(field, '').strip()
            if not value:
                raise ValueError(f"Missing recipe {field}")
            setattr(recipe, field, value)
            
        recipe.description = request.form.get('description') or None
        recipe.notes = request.form.get('notes') or None
        
        int_fields = ['prep_time', 'cook_time', 'total_time',
                      'servings', 'rating']
        for field in int_fields:
            value = request.form.get(field, '')
            if value.isdigit():
                setattr(recipe, field, int(value))
        
        if not recipe.total_time:
            recipe.total_time = sum([recipe.prep_time or 0,
                                     recipe.cook_time or 0]) or None
        
        if 'image_file' in request.files:
            file = request.files['image_file']
            if (file and file.filename != '' and allowed_file(file.filename)):
                filename = handle_image_upload(file,
                                               target_folder=get_image_folder(),
                                               prefix="manual")
                # Remove any old/temporary source file 
                # and point to the downloaded local/named image
                if filename:
                    if recipe.image_url:
                        try:
                            os.remove(os.path.join(get_image_folder(),
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

        # If this is a brand-new recipe, add and flush it FIRST
        # This forces the database to generate an ID for it 
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
        
        flash(
            f"{ICON['SUCCESS']}"
            f" <b>{recipe.title}</b> was saved successfully!",
            "success"
        )
        return redirect(url_for('recipes.view_recipe',
                                recipe_id=recipe.id))
    
    except Exception as e:
        flash(f"{ICON['FAIL']} {e}", "error")
        return redirect(url_for('recipes.index'))


@recipe_bp.route('/import_url', methods=['POST'])
def import_url():
    url = request.form.get('url')
    if url:
        extracted = scrape_recipe_from_url(url)
        if extracted:
            title = extracted.get('title')
            if recipe_exists(title, url):
                flash(
                    f"{ICON['FAIL']} Recipe"
                    f" <b>{title}</b> already exists.",
                    "error"
                )
            else:
                parsed_url = urlparse(url)
                domain_name = parsed_url.netloc.lower().replace('www.', '')
                
                # Download and save the image locally
                local_image_name = download_and_cache_image(
                    external_img_url=extracted.get('image_url'),
                    target_folder=get_image_folder(),
                    title=extracted.get('title'),
                )
                
                new_recipe = Recipe(
                    title=f"{title}",
                    source_url=url,
                    ingredients=extracted.get('ingredients'),
                    instructions=extracted.get('instructions'),
                    image_url=local_image_name,   # Local filename not web URL
                    description=extracted.get('description'),
                    servings=extracted.get('servings'),
                )
                db.session.add(new_recipe)
                db.session.commit()
                flash(
                    f"{ICON['SUCCESS']} Successfully imported"
                    f" <b>{title}</b> from <i>{domain_name}</i>!",
                    "success"
                )
        else:
            flash(
                f"{ICON['FAIL']} Failed to parse recipe"
                f" from the provided URL link.",
                "error"
            )
    return redirect(url_for('recipes.index'))


@recipe_bp.route('/delete/<int:recipe_id>', methods=['POST'])
def delete_recipe(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    if recipe.image_url:
        try:
            os.remove(os.path.join(get_image_folder(), recipe.image_url))
        except OSError:
            pass
    db.session.delete(recipe)
    db.session.commit()
    return redirect(url_for('recipes.index'))


@recipe_bp.route('/scan/start', methods=['POST'])
def scan_start():
    """Initialize a multi-page scanning session."""
    draft_id = str(uuid.uuid4())
    OCR_DRAFTS[draft_id] = {
        'title': 'New Scanned Recipe',
        'raw_chunks': [],
        'metadata': {},
    }
    return jsonify({'draft_id': draft_id, 'message': 'Scan session started.'})


@recipe_bp.route('/scan/append/<draft_id>', methods=['POST'])
def scan_append(draft_id):
    """Process an incoming image page and append it to the draft."""
    if draft_id not in OCR_DRAFTS:
        return jsonify({'error': 'Invalid or expired scanning session ID'}), 404
    if 'image' not in request.files:
        return jsonify({'error': 'No image file provided'}), 400
    image_file = request.files['image']
    temp_path = f'/tmp/{uuid.uuid4()}.jpg'
    image_file.save(temp_path)


@recipe_bp.route('/scan/finish/<draft_id>', methods=['POST'])
def scan_finish(draft_id):
    """Combines scan pages into a final recipe."""
    if draft_id not in OCR_DRAFTS:
        return jsonify({'error': 'Draft not found'}), 404
    draft = OCR_DRAFTS[draft_id]
    complete_raw_text = "\n\n--- NEXT PAGE ---\n\n".join(draft['raw_chunks'])
    # send to recipe parser
    del OCR_DRAFTS[draft_id]
    return jsonify({
        'status': 'success',
        'raw_text_combined': complete_raw_text,
        # 'recipe': structured_recipe,
    })


@recipe_bp.route('/scan_ocr', methods=['POST'])
def scan_ocr():
    """
    Accepts a single or multiple uploaded images of cookbook/magazine pages.
    Runs them through the multi-page OCR engine sequentially and returns 
    a structured JSON response to pre-populate the recipe creation form.
    """
    if 'image_files' not in request.files:
        return jsonify({"error": "No image files provided in the request"}), 400
        
    uploaded_files = request.files.getlist('image_files')
    
    # Filter out empty form submissions
    valid_files = [f for f in uploaded_files if f and f.filename != '']
    if not valid_files:
        return jsonify({"error": "No files selected for scanning"}), 400

    saved_local_paths = []
    saved_web_filenames = []
    
    try:
        # Iterate and convert/save all incoming book pages safely
        for index, file_storage in enumerate(valid_files):
            if not allowed_file(file_storage.filename):
                continue
                
            # Get the clean filename string saved into IMAGE_FOLDER
            saved_filename = handle_image_upload(file_storage,
                                                 prefix=f"scan_p{index+1}")
            
            if saved_filename:
                full_path = os.path.join(get_image_folder(), saved_filename)
                saved_local_paths.append(full_path)
                saved_web_filenames.append(saved_filename)

        if not saved_local_paths:
            err_str = "No valid or allowed images could be processed"
            return jsonify({"error": err_str}), 400

        # Fire the optimized multi-page text extraction pipeline
        extracted_text_blob = extract_text_from_pages(saved_local_paths)

        # Shape Analysis: Attempt to isolate an illustration/photo out of Page 1
        # Cookbook layouts typically place the dish hero photo on the first page
        isolated_dish_image = isolate_and_crop_embedded_image(
            source_image_path=saved_local_paths[0], 
            upload_folder=get_image_folder(),
        )

        # If no specific inside crop was found, 
        # fallback to the entire first page image
        final_recipe_image = (isolated_dish_image if isolated_dish_image else 
                              saved_web_filenames[0])

        # Return structured text to the frontend editor form
        # Interactive: the user reviews the text before hitting "Save"
        return jsonify({
            "status": "success",
            "extracted_text": extracted_text_blob,
            "assigned_image": final_recipe_image,
            "message": (f"{ICON['SUCCESS']} Successfully processed"
                        f" {len(saved_local_paths)} cookbook page(s)."
            )
        })

    except Exception as e:
        print(f"Flask Multi-Page OCR Route failure: {e}")
        return jsonify({"error": f"Internal server processing failure: {e}"}), 500
