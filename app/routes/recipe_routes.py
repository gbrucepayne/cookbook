import os
import secrets
import uuid
from urllib.parse import urlparse

import pillow_heif
import requests
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
from PIL import Image
from werkzeug.utils import secure_filename

from app import db
from app.models import Recipe
from app.ocr import extract_text_from_pages, isolate_and_crop_embedded_image
from app.scraper import scrape_recipe_from_url

recipe_bp = Blueprint('recipes', __name__)

MAIN_PAGE = 'recipes.html'


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']


def handle_image_upload(file_storage, prefix="manual"):
    """
    Saves an uploaded file safely. If it's a HEIC file from an iPhone,
    converts it to a web-friendly JPEG before writing to disk.
    Returns the final saved filename string.
    """
    if not file_storage or file_storage.filename == '':
        return None
        
    filename = secure_filename(file_storage.filename)
    base_name, ext = os.path.splitext(filename)
    ext = ext.lower()
    
    if ext in ['.heic', '.heif']:
        # Generate target name pointing to progressive web-safe jpeg
        target_filename = f"{prefix}_{base_name}.jpg"
        full_dest_path = os.path.join(current_app.config['IMAGE_FOLDER'], target_filename)
        
        try:
            # Open HEIC file directly via pillow-heif plugin integration wrapper
            heif_file = pillow_heif.read_heif(file_storage.stream)
            image = Image.frombytes(
                heif_file.mode, 
                heif_file.size, 
                heif_file.data, 
                "raw", 
                heif_file.mode, 
                heif_file.stride,
            )
            # Save converted asset cleanly with high-grade compression matching web targets
            image.save(full_dest_path, "JPEG", quality=85)
            return target_filename
        except Exception as e:
            print(f"HEIC image conversion pipeline error: {e}")
            return None
    else:
        # Standard web file type management (JPG, PNG, WebP)
        target_filename = f"{prefix}_{filename}"
        file_storage.save(os.path.join(current_app.config['IMAGE_FOLDER'], target_filename))
        return target_filename


def download_and_cache_image(external_img_url, title=""):
    """
    Downloads an external web image and writes it locally to the server upload folder.
    Returns the newly created local filename string, or None if download fails.
    """
    if not external_img_url:
        return None
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}
        response = requests.get(external_img_url, headers=headers, timeout=10, stream=True)
        response.raise_for_status()
        
        # Deduce file extension from URL or fallback to jpeg
        ext = '.jpg'
        for allowed_ext in current_app.config['ALLOWED_EXTENSIONS']:
            if f".{allowed_ext}" in external_img_url.lower():
                ext = f".{allowed_ext}"
                break
                
        # Generate a collision-free filename asset token
        random_hex = secrets.token_hex(8)
        if title and not title.endswith("_"):
            title = title.replace(' ', '_').replace('-', '_').lower() + '_'
        local_filename = f"{title}scraped_{random_hex}{ext}"
        full_dest_path = os.path.join(current_app.config['IMAGE_FOLDER'], local_filename)
            
        
        # Stream the image file bits chunks safely onto server storage
        with open(full_dest_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                
        return local_filename
    except Exception as e:
        print(f"Failed to locally archive image asset: {e}")
        return None


@recipe_bp.route('/')
def index():
    """The Home page."""
    search_query = request.args.get('q', '').strip()
    if search_query:
        recipes = Recipe.query.filter(
            (Recipe.title.ilike(f'%{search_query}%')) | 
            (Recipe.ingredients.ilike(f'%{search_query}%')) |
            (Recipe.description.ilike(f'%{search_query}%'))
        ).all()
    else:
        recipes = Recipe.query.all()
    return render_template(MAIN_PAGE, recipes=recipes, recipe=None, search_query=search_query, is_editing=False)


@recipe_bp.route('/recipe/<int:recipe_id>')
def view_recipe(recipe_id):
    """Display the specified recipe."""
    recipe = Recipe.query.get_or_404(recipe_id)
    return render_template(MAIN_PAGE, recipes=[], recipe=recipe, search_query='', is_editing=False)


@recipe_bp.route('/recipe/<int:recipe_id>/edit')
def edit_recipe_form(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    return render_template(MAIN_PAGE, recipes=[], recipe=recipe, search_query='', is_editing=True)


@recipe_bp.route('/recipe/<int:recipe_id>/update', methods=['POST'])
def update_recipe(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    
    recipe.title = request.form.get('title')
    recipe.ingredients = request.form.get('ingredients')
    recipe.instructions = request.form.get('instructions')
    recipe.description = request.form.get('description')
    recipe.rating = int(request.form.get('rating', 0))
    recipe.notes = request.form.get('notes')
    recipe.servings = request.form.get('servings')
    recipe.prep_time = request.form.get('prep_time')
    recipe.cook_time = request.form.get('cook_time')
    
    if 'image_file' in request.files:
        file = request.files['image_file']
        if file and file.filename != '' and allowed_file(file.filename):
            filename = secure_filename(handle_image_upload(file, prefix="manual"))
            # file.save(os.path.join(current_app.config['IMAGE_FOLDER'], filename))   # redundant
            # Remove the temporary source file and point to the downloaded local/named image
            if recipe.image_url:
                try:
                    os.remove(os.path.join(current_app.config['IMAGE_FOLDER'], recipe.image_url))
                except OSError:
                    pass
            recipe.image_url = filename

    db.session.commit()
    return redirect(url_for('recipes.view_recipe', recipe_id=recipe.id))


@recipe_bp.route('/add_manual', methods=['POST'])
def add_manual():
    title = request.form.get('title')
    ingredients = request.form.get('ingredients')
    instructions = request.form.get('instructions')
    description = request.form.get('description')
    notes = request.form.get('notes')
    rating = int(request.form.get('rating', 0))
    servings = request.form.get('servings')
    prep_time = request.form.get('prep_time')
    cook_time = request.form.get('cook_time')
    
    image_filename = None
    if 'image_file' in request.files:
        file = request.files['image_file']
        if file and file.filename != '' and allowed_file(file.filename):
            filename = secure_filename(handle_image_upload(file, prefix="manual"))
            # file.save(os.path.join(current_app.config['IMAGE_FOLDER'], filename))   # redundant
            image_filename = filename

    if title and ingredients and instructions:
        new_recipe = Recipe(
            title=title,
            ingredients=ingredients,
            instructions=instructions,
            image_url=image_filename,
            description=description,
            notes=notes,
            rating=rating,
            servings=servings,
            prep_time=prep_time,
            cook_time=cook_time,
        )
        db.session.add(new_recipe)
        db.session.commit()
        flash(f"🎉 '{title}' was saved successfully!", "success")
    return redirect(url_for('recipes.index'))


@recipe_bp.route('/import_url', methods=['POST'])
def import_url():
    url = request.form.get('url')
    if url:
        extracted = scrape_recipe_from_url(url)
        if extracted:
            parsed_url = urlparse(url)
            domain_name = parsed_url.netloc.lower().replace('www.', '')
            title = extracted.get('title')
            
            # Download and save the image locally
            local_image_name = download_and_cache_image(
                extracted.get('image_url'),
                extracted.get('title'),
            )
            
            new_recipe = Recipe(
                title=f"{title} ({domain_name})",
                source_url=url,
                ingredients=extracted.get('ingredients'),
                instructions=extracted.get('instructions'),
                image_url=local_image_name,   # Saves local cached filename instead of raw web URL
                description=extracted.get('description'),
                servings=extracted.get('servings'),
            )
            db.session.add(new_recipe)
            db.session.commit()
            flash(f"📥 Successfully imported '{title}' from {domain_name}!", "success")
        else:
            flash("❌ Failed to parse recipe from the provided URL link.", "error")
    return redirect(url_for('recipes.index'))


@recipe_bp.route('/delete/<int:recipe_id>', methods=['POST'])
def delete_recipe(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    if recipe.image_url:
        try:
            os.remove(os.path.join(current_app.config['IMAGE_FOLDER'], recipe.image_url))
        except OSError:
            pass
    db.session.delete(recipe)
    db.session.commit()
    return redirect(url_for('recipes.index'))


# @recipe_bp.route('/import_photo', methods=['POST'])
# def import_photo():
#     if 'photo_file' not in request.files:
#         flash("❌ No file part selected.", "error")
#         return redirect(url_for('recipes.index'))
        
#     file = request.files['photo_file']
#     if file.filename == '' or not allowed_file(file.filename):
#         flash("❌ Invalid or missing image file choice.", "error")
#         return redirect(url_for('recipes.index'))
        
#     # 1. Securely save the uploaded picture to disk
#     filename = secure_filename(handle_image_upload(file, prefix="ocr"))
#     saved_path = os.path.join(current_app.config['IMAGE_FOLDER'], filename)
    
#     # 2. Advanced OpenCV Pipeline: Look for a sub-image nested inside the page scan
#     dish_image_filename = isolate_and_crop_embedded_image(saved_path, current_app.config['IMAGE_FOLDER'])
    
#     # If a distinct embedded photo was isolated, use it as the main recipe display picture.
#     # Otherwise, fall back to displaying the entire full page scan image.
#     recipe_image = dish_image_filename
    
#     # 2. Extract text from the image
#     scanned_text = extract_text_from_image(saved_path)
    
#     if not scanned_text:
#         flash("⚠️ Image uploaded but word parsing failed. Is Tesseract installed?", "error")
#         scanned_text = "Could not parse text automatically. Type your ingredients and steps here."

#     # 3. Create a temporary draft recipe to display on the edit screen
#     # This allows you to easily format the raw scanned text into ingredients and instructions.
#     draft_recipe = Recipe(
#         title="New Scanned Photo Recipe (Draft)",
#         ingredients=scanned_text, # Drop the text dump here to easily cut/paste
#         instructions="Review the raw scanned text on the left pane and format it correctly.",
#         image_url=recipe_image
#     )
    
#     # Temporarily save the record to provide an ID for the edit page context loop
#     db.session.add(draft_recipe)
#     db.session.commit()
#     os.remove(saved_path)
    
#     flash("📸 Photo scanned successfully! Please format the parsed text blocks below.", "success")
#     return redirect(url_for('recipes.edit_recipe_form', recipe_id=draft_recipe.id))

OCR_DRAFTS = {}


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
        # 1. Iterate and convert/save all incoming book pages safely
        for index, file_storage in enumerate(valid_files):
            if not allowed_file(file_storage.filename):
                continue
                
            # Use your existing wrapper function to convert HEIC or store standard files
            # This returns just the clean filename string saved into IMAGE_FOLDER
            saved_filename = handle_image_upload(file_storage, prefix=f"scan_p{index+1}")
            
            if saved_filename:
                full_path = os.path.join(current_app.config['IMAGE_FOLDER'], saved_filename)
                saved_local_paths.append(full_path)
                saved_web_filenames.append(saved_filename)

        if not saved_local_paths:
            return jsonify({"error": "No valid or allowed images could be processed"}), 400

        # 2. Fire the optimized multi-page text extraction pipeline
        extracted_text_blob = extract_text_from_pages(saved_local_paths)

        # 3. Shape Analysis: Attempt to isolate an illustration/photo out of Page 1
        # Cookbook layouts typically place the dish hero photo on the primary page layout
        isolated_dish_image = isolate_and_crop_embedded_image(
            source_image_path=saved_local_paths[0], 
            upload_folder=current_app.config['IMAGE_FOLDER']
        )

        # 4. Fallback Image Assignment
        # If no specific inside crop was found, fallback to the entire first page image
        final_recipe_image = isolated_dish_image if isolated_dish_image else saved_web_filenames[0]

        # 5. Return structured text to the frontend editor form
        # This keeps things highly interactive: the user reviews the text before hitting "Save"
        return jsonify({
            "status": "success",
            "extracted_text": extracted_text_blob,
            "assigned_image": final_recipe_image,
            "message": f"Successfully processed {len(saved_local_paths)} cookbook page(s)."
        })

    except Exception as e:
        print(f"Flask Multi-Page OCR Route failure: {e}")
        return jsonify({"error": f"Internal server processing failure: {e}"}), 500
