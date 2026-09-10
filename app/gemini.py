"""Gen AI recipe extraction using Gemini.
"""
import io
import json
import logging
import os
import time

from google import genai
from google.genai import errors
from PIL import Image

from app.image import optimize_and_save_image_stream
from app.models import Recipe

logger = logging.getLogger(__name__)


def extract_recipe_genai(image_paths: list[str],
                         image_folder: str,
                         max_retries: int = 3,
                         initial_delay: int = 2,
                         ) -> Recipe:
    """Use GenAI to attempt to extract recipe data from images."""
    client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))
    uploaded_files = []
    for image_path in image_paths:
        if not os.path.exists(image_path):
            raise ValueError(f"Invalid image path {image_path}")
        logger.debug("Uploading image: %s...", image_path)
        uploaded_file = client.files.upload(file=image_path)
        uploaded_files.append(uploaded_file)

    prompt = (
        "These images show a single recipe split across multiple pages. "
        "Please read all pages and extract the complete recipe "
        "into a single, cohesive structure (JSON). "
        "Include the recipe 'title', full 'ingredients' list, "
        "and step-by-step 'instructions' where single-quoted labels are keys. "
        "If a completed dish image is identifiable provide its exact normalized "
        "bounding box coordinates under a 'dish_image_box' key "
        "formatted exactly as [ymin, xmin, ymax, xmax] "
        "integers scaled from 0 to 1000, and the 'dish_image_index' of the page."
        "If possible also extract 'prep_time', 'cook_time' and 'total_time' "
        "(total = preparation + cooking). "
        "Return any text not included in the above as a notes block."
    )
    
    delay = initial_delay
    genai_models = [
        'gemini-3.5-flash',
        'gemini-3.6-flash',
        'gemini-flash-latest',
    ]
    for attempt in range(max_retries):
        try:
            genai_model = genai_models[attempt % len(genai_models)]
            response = client.models.generate_content(
                model=genai_model,
                contents=[uploaded_files, prompt],
                # config=types.GenerateContentConfig(response_mime_type='application/json'),
                config={'response_mime_type': 'application/json'},
            )
            break
        except errors.ServerError as e:
            if attempt == max_retries - 1:
                raise
            logger.error("Attempt %d failed: %s", attempt + 1, e)
            time.sleep(delay)
            delay *= 2
    
    logger.debug("Gemini response: %s", response.text)
    recipe_data = json.loads(response.text)
    if not isinstance(recipe_data, dict):
        raise TypeError(f"Unsupported data format: {response.text}")
    
    recipe = Recipe(
        title=recipe_data.get('title'),
        ingredients=recipe_data.get('ingredients'),
        instructions=recipe_data.get('instructions'),
    )
    required = ['title', 'ingredients', 'instructions']
    for attr in required:
        if not getattr(recipe, attr):
            raise ValueError(f"Invalid recipe missing {attr}")

    # Extract the returned dish/hero image bounding box coordinates
    image_box = recipe_data.get("dish_image_box")
    if image_box:
        raw_image_index = recipe_data.get("dish_image_index")
        if not isinstance(raw_image_index, int):
            raise ValueError(f"Invalid image index: {raw_image_index}")
        raw_image = Image.open(image_paths[raw_image_index])
        width, height = raw_image.size
        
        # De-normalize coordinates from 0-1000 scale back to actual pixel dimensions
        ymin, xmin, ymax, xmax = image_box
        left = int((xmin / 1000) * width)
        top = int((ymin / 1000) * height)
        right = int((xmax / 1000) * width)
        bottom = int((ymax / 1000) * height)
        
        # Crop the image to send stream to common file optimizer
        dish_image = raw_image.crop((left, top, right, bottom))
        image_stream = io.BytesIO()
        dish_image.save(image_stream, format="WEBP")
        image_stream.seek(0)
        filename_base = recipe.title.lower().replace(' ', '_').replace('-', '_')
        recipe.image_url = optimize_and_save_image_stream(
            stream=image_stream,
            filename_base=filename_base,
            target_folder=image_folder,
            suffix='scan',
        )
        if recipe.image_url:
            logger.info("Dish image saved for %s", recipe.title)
    else:
        logger.debug("Dish image boundary could not be identified.")

    return recipe
