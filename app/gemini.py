"""Gen AI recipe extraction using Gemini.
"""
import io
import json
import logging
import os
import re
import time

from google import genai
from google.genai import errors, types
from PIL import Image

from app.image import optimize_and_save_image_stream
from app.models import Recipe, required_fields, set_field_value, valid_fields

logger = logging.getLogger(__name__)

MODEL_ATTEMPT_LIMIT = 4
ATTEMPT_TIMEOUT_SEC = 90


def _get_model_version(model_name):
    """Extract the Gemini model version (for sorting)."""
    match = re.search(r'gemini-(\d+)\.(\d+)', model_name)
    if match:
        return (int(match.group(1)), int(match.group(2)))
    match_single = re.search(r'gemini-(\d+)', model_name)
    if match_single:
        return (int(match_single.group(1)), 0)
    return (0, 0)


def extract_recipe_genai(image_paths: list[str],
                         image_folder: str,
                         max_retries: int = MODEL_ATTEMPT_LIMIT,
                         initial_delay: int = 5,
                         ) -> Recipe:
    """Use GenAI to attempt to extract recipe data from images."""
    client = genai.Client(
        api_key=os.getenv('GEMINI_API_KEY'),
        http_options=types.HttpOptions(timeout=ATTEMPT_TIMEOUT_SEC*1000),
    )
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
        "When extracting ingredients, convert any single-character unicode "
        "fractions (like ¼, ½) into plain text slash formats (like 1/4, 1/2) "
        "before serializing the text into the JSON structure. "
        "If a completed dish image is identifiable, provide its exact normalized "
        "bounding box coordinates under a 'dish_image_box' key "
        "formatted exactly as [ymin, xmin, ymax, xmax] "
        "integers scaled from 0 to 1000, and the 'dish_image_index' of the page."
        "If possible, also extract 'prep_time', 'cook_time' and 'total_time' "
        "keys with values in minutes. "
        "Return any text not included in the above as a notes block. "
        # "To adhere to formatting constraints, summarize and rephrase the "
        # "extracted 'instructions' steps into clear, actionable shorthand "
        # "sentences rather than transcribing the paragraphs verbatim from the page. "
    )
    
    delay = initial_delay
    supported_models = []
    for model in client.models.list():
        if 'generateContent' in model.supported_actions:
            name = model.name.replace('models/', '')
            if name.endswith(('-flash', '-flash-latest')):
                supported_models.append(name)
    sorted_models = sorted(supported_models,
                           key=_get_model_version,
                           reverse=True)
    genai_models = sorted_models[:MODEL_ATTEMPT_LIMIT]
    if len(genai_models) == 0:
        raise ValueError('Unable to derive supported Gemini models')
    for attempt in range(max_retries):
        try:
            genai_model = genai_models[attempt % len(genai_models)]
            logger.info("Querying GenAI model %s", genai_model)
            response = client.models.generate_content(
                model=genai_model,
                contents=[uploaded_files, prompt],
                config={'response_mime_type': 'application/json'},
            )
            if not response.text:
                logger.error("Model %s returned empty. Finish: %s. Safety: %s",
                             genai_model,
                             response.candidates[0].finish_reason,
                             response.candidates[0].safety_ratings)
                raise RuntimeError(f"AI prompt returned empty ({genai_model})")
            logger.debug("Gemini response: %s", response.text)
            break
        except errors.ServerError as e:
            logger.error("Attempt %d (%s) failed: %s",
                         attempt + 1, genai_model, e)
            if attempt == max_retries - 1:
                raise RuntimeError(f"AI retries ({max_retries}) exhausted")
            time.sleep(delay)
            delay *= 2
    
    recipe_data = json.loads(response.text)
    if not isinstance(recipe_data, dict):
        raise TypeError(f"Unsupported data format: {response.text}")
    
    recipe = Recipe()
    for field in valid_fields():
        if field not in recipe_data:
            if field in required_fields():
                raise ValueError(f"Invalid recipe - missing {field}")
            continue
        set_field_value(recipe, field, recipe_data.get(field))

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
