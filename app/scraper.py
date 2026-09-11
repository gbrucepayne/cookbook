"""Web Recipe scraper utilities.
"""

import json
import logging
import re
import time
from enum import Enum
from typing import Any

# import requests
from bs4 import BeautifulSoup
from curl_cffi import requests
from curl_cffi.requests.errors import RequestsError
from recipe_scrapers import scrape_html

from app.ingredient import normalize_unicode_fractions
from app.models import Recipe

logger = logging.getLogger(__name__)


def _css_class_filter(class_list: list[str],
                      descendant_mode: bool = True) -> str:
    """
    Takes a list of class strings and turns them into a case-insensitive 
    CSS substring selector string.
    """
    # Loop through list, strip whitespaces, and format the CSS string fragment
    # The 'i' flag at the end forces case-insensitivity in modern CSS engines
    fragments = [f'[class*="{cls.strip()}" i]' 
                 for cls in class_list if cls.strip()]
    # Space ' ' means nesting/descendants.
    # Empty string '' means compound selectors on one element.
    delimiter = ' ' if descendant_mode else ''
    return delimiter.join(fragments)


def extract_image_url(meta: dict[str, Any]|BeautifulSoup) -> str|None:
    """Extract the recipe image link."""
    image_url = None
    # Recipe Schema
    if isinstance(meta, dict):
        img_data = meta.get('image')
        if isinstance(img_data, list) and img_data:
            image_url = img_data[0]
        elif isinstance(img_data, dict):
            image_url = img_data.get('url')
        elif isinstance(img_data, str):
            image_url = img_data
    # Fallback to soup
    if not image_url and isinstance(meta, BeautifulSoup):
        og_image = meta.find('meta', property='og:image')
        if og_image and og_image.get('content'):
            image_url = og_image['content']
        else:
            # Fallback to the first large structural layout image 
            # within the content body
            img_tags = ['hero', 'recipe', 'wp-post-image']
            img_tag = meta.find('img', 
                                class_=lambda c: c and any(x in c.lower() 
                                                           for x in img_tags))
            if img_tag and img_tag.get('src'):
                image_url = img_tag['src']
    return image_url


def get_list_following(heading_text: str, soup: BeautifulSoup) -> list[str]:
    tags = ['h1', 'h2', 'h3', 'h4', 'div']
    heading = soup.find(lambda tag: tag.name in tags and 
                        heading_text.strip().lower() == tag.text.strip().lower())
    if heading:
        target_list = heading.find_next(['ul', 'ol'])
        if target_list:
            return [li.text.strip() for li in target_list.find_all('li')]
    return []


def extract_ingredients(meta: dict[str, Any]|BeautifulSoup) -> list[str]|None:
    """Extract ingredients from a candidate text string/block."""
    ingredients: list[str] = []
    # Recipe Schema
    if isinstance(meta, dict):
        tags = ['recipeIngredient']
        for tag in tags:
            candidate = meta.get(tag)
            if not candidate:
                continue
            if isinstance(candidate, list):
                ingredients = list(
                    dict.fromkeys(ingredients + candidate)
                )
            elif isinstance(candidate, str) and candidate not in ingredients:
                ingredients.append(candidate)
            break
    # Fallback to soup
    if not ingredients and isinstance(meta, BeautifulSoup):
        ingredients = get_list_following('Ingredients', meta)
        if not ingredients:
            classes = ['ingredient', 'recipe-ing', 'wprm-recipe-ingredient']
            section_headers = ('ingredients',)
            for el in meta.select(_css_class_filter(classes)):
                candidate = el.text.strip()
                if '\n' in candidate:
                    for i, c in enumerate(candidate.split('\n')):
                        item = c.strip()
                        if item:
                            if i == 1 and item.lower().startswith(section_headers):
                                continue
                            if item not in ingredients:
                                ingredients.append(item)
                elif candidate and candidate not in ingredients:
                    ingredients.append(candidate)
    return '\n'.join(ingredients) if ingredients else None
    # formatted = [scale_ingredient_line(i) for i in ingredients]
    # return formatted


def extract_instructions(meta: dict[str, Any]|BeautifulSoup) -> list[str]|None:
    """Extract instructions from a candidate text string/block."""
    instructions: list[str] = []
    # Recipe Schema
    if isinstance(meta, dict):
        tags = ['recipeInstructions']
        for tag in tags:
            candidate = meta.get(tag)
            if not candidate:
                continue
            if isinstance(candidate, list):
                if all(isinstance(item, dict) for item in candidate):
                    item_list: list[dict[str, Any]] = []
                    for item in candidate:
                        item_type = item.get('@type')
                        if item_type in ['HowToSection']:
                            item_list = item.get('itemListElement')
                            if not isinstance(item_list, list):
                                raise ValueError(
                                    f"Unexpected structure: {candidate}"
                                )
                        elif item_type in ['HowToStep']:
                            item_list.append(item)
                    candidate = [step.get('text') 
                                 for step in item_list if step.get('text')]
                else:
                    raise ValueError(f"Unexpected structure: {candidate}")
            elif isinstance(candidate, str):
                candidate = [i.strip() 
                             for i in candidate.split('\n') if i.strip()]
            instructions = list(dict.fromkeys(instructions + candidate))
            break
    # Fallback to soup
    if not instructions and isinstance(meta, BeautifulSoup):
        instructions = get_list_following('Instructions', meta)
        if not instructions:
            classes = ['instruction', 'step', 'direction', 
                    'wprm-recipe-instruction', 'preparation']
            headers = ('instructions',)
            step_number_pattern = r'^\s*\d+(?!\s*[\/\.])[\s\.\-\–\—:]*'
            for el in meta.select(_css_class_filter(classes)):
                candidate = el.text.strip()
                if '\n' in candidate:
                    for i, c in enumerate(candidate.split('\n')):
                        item = c.strip()
                        if item:
                            if i == 1 and item.lower().startswith(headers):
                                continue
                            if item not in instructions:
                                instructions.append(item)
                elif candidate and candidate not in instructions:
                    instructions.append(candidate)
            instructions = [re.sub(step_number_pattern, '', instruction)
                            for instruction in instructions]
    return '\n'.join(instructions) if instructions else None


def extract_servings(meta: dict[str, Any]|BeautifulSoup) -> int|None:
    """Extract number of servings."""
    servings = None
    if isinstance(meta, dict):
        tags = ['recipeYield', 'servings']
        for tag in tags:
            candidate = meta.get(tag)
            if candidate:
                servings = candidate
                break
    if not servings and isinstance(meta, BeautifulSoup):
        classes = ['wprm-recipe-servings']
        for el in meta.select(_css_class_filter(classes)):
            candidate = el.text.strip()
            if el.name == 'input' or el.has_attr('value'):
                servings = el.get('value', '').strip()
            elif el.has_attr('data-servings'):
                servings = el.get('data-servings', '').strip()
            else:
                servings = candidate
            if servings:
                break
    if servings:
        servings = int(re.search(r'\d+', servings).group())
    return servings


class TimeType(Enum):
    PREP = "prep"
    COOK = "cook"
    TOTAL = "total"

    
def _recipe_schema_time(time_val: str) -> int|None:
    """Derive time value in minutes from a Recipe Schema."""
    if isinstance(time_val, str) and time_val:
        candidate = int(re.search(r'\d+', time_val).group())
        if time_val.endswith(('M', 'Minutes')):
            return candidate
    return None


def extract_recipe_time(meta: dict[str, Any]|BeautifulSoup,
                        time_type = TimeType.TOTAL) -> int|None:
    """Extract the time based on tag/type."""
    if time_type == TimeType.PREP:
        tags = ['prepTime']
        classes = ['wprm-recipe-prep_time-minutes']
    elif time_type == TimeType.COOK:
        tags = ['cookTime']
        classes = ['wprm-recipe-cook_time-minutes']
    else:
        tags = ['totalTime']
        classes = ['wprm-recipe-total_time-minutes']
    timeval = None
    if isinstance(meta, dict):
        for tag in tags:
            candidate = meta.get(tag)
            if candidate:
                timeval = _recipe_schema_time(candidate)
                break
    if not timeval and isinstance(meta, BeautifulSoup):
        for el in meta.select(_css_class_filter(classes)):
            candidate = el.text.strip()
            if candidate:
                timeval = int(re.search(r'\d+', candidate).group())
                break
    return timeval


def extract_total_time(meta) -> int|None:
    return extract_recipe_time(meta, TimeType.TOTAL)


def extract_cook_time(meta) -> int|None:
    return extract_recipe_time(meta, TimeType.COOK)


def extract_prep_time(meta) -> int|None:
    return extract_recipe_time(meta, TimeType.PREP)


def scrape_recipe_from_url(url) -> Recipe:
    """
    Fetches a remote URL and attempts to parse recipe content.
    Returns a dictionary of extracted fields, 
    or None if it completely fails.
    """
    try:
        recipe_html = fetch_recipe_html_safe(url)
        
        recipe = Recipe(source_url=url)
        required = ['title', 'ingredients', 'instructions']
        opt_text = ['image_url', 'description']
        opt_int = ['servings', 'total_time', 'prep_time', 'cook_time']
        
        list_as_str = ['ingredients', 'instructions']
        
        try:
            scraped = scrape_html(recipe_html,
                                  org_url=url,
                                  supported_only=False)
            scraper_map = {
                'image_url': 'image',
                'servings': 'yields',
            }
            for attr in required + opt_text + opt_int:
                func_name = scraper_map.get(attr, attr)
                try:
                    func = getattr(scraped, func_name, None)
                    if func and callable(func):
                        value = func()
                        if attr in list_as_str and isinstance(value, list):
                            value = '\n'.join(value)
                        setattr(recipe, attr, value)
                except Exception as e:
                    logger.error(f"Failed to parse {attr}: {e}")
            logger.debug("Parsed %s using 'recipe-scrapers' package (%s)",
                         recipe.title, url)
        except Exception as e:
            logger.info(f"Unable to parse using 'recipe-scrapers': {e}")
        
        if not recipe.ingredients or not recipe.instructions:
            soup = BeautifulSoup(recipe_html, 'html.parser')
            
            title_el = soup.find('meta', 'og:title') or soup.find('h1')
            if title_el and title_el.text:
                recipe.title = title_el.text.strip()
            else:
                raise ValueError(f'Unable to parse title from {url}')
            desc_meta = soup.find('meta', property='og:description')
            if desc_meta and isinstance(desc_meta.attrs, dict):
                recipe.description = desc_meta.attrs.get('content')
            
            attrs = ['ingredients', 'instructions', 'image_url',
                    'servings', 'total_time', 'cook_time', 'prep_time']

            # Look for standardized Recipe Schema
            schema_tags = soup.find_all('script', type='application/ld+json')
            for tag in schema_tags:
                try:
                    if not tag.string:
                        continue
                    data = json.loads(tag.string)
                    # JSON-LD can be a single dictionary or a list of schemas
                    schemas = data if isinstance(data, list) else [data]
                    if (isinstance(data, dict) and 
                        isinstance(data.get('@graph'), list)):
                        graph = data.get('@graph')
                        if (all(isinstance(x, dict) for x in graph) and
                            any(x.get('@type') == 'Recipe' for x in graph)):
                            schemas = data['@graph']
                    for schema in schemas:
                        # Look for explicit Recipe objects
                        if schema.get('@type') == 'Recipe':
                            for attr in attrs:
                                parsed = getattr(recipe, attr)
                                if not parsed:
                                    func = globals().get(f'extract_{attr}')
                                    if func and callable(func):
                                        setattr(recipe, attr, func(schema))
                            break
                        if recipe.ingredients:
                            logger.debug("Parsed %s using Recipe schema (%s)",
                                         recipe.title, url)
                except Exception as e:
                    logger.error(e)
                    continue
            
            brute_force = False
            for attr in attrs:
                parsed = getattr(recipe, attr)
                if not parsed:
                    brute_force = True
                    func = globals().get(f'extract_{attr}')
                    if func and callable(func):
                        setattr(recipe, attr, func(soup))
            if brute_force:
                logger.debug("Parsed %s using raw HTML tags (%s)",
                             recipe.title, url)
        
        if not recipe.ingredients:
            raise ValueError(f'Unable to parse ingredients from {url}')
        if not recipe.instructions:
            raise ValueError(f'Unable to parse instructions from {url}')
        
        # Normalize ingredients format for storage
        normal_ingredients = [normalize_unicode_fractions(ingredient)
                              for ingredient in recipe.ingredients.split('\n')]
        recipe.ingredients = '\n'.join(normal_ingredients)

        for attr in opt_int:
            value = getattr(recipe, attr, None)
            if value and not isinstance(value, int):
                match = re.match(r'^\s*(\d+)', value.strip())
                value = int(match.group(1)) if match else None
                setattr(recipe, attr, value)
        
        if not recipe.total_time and (recipe.prep_time or recipe.cook_time):
            if recipe.prep_time:
                recipe.total_time = recipe.prep_time
            if recipe.cook_time:
                if not recipe.total_time:
                    recipe.total_time = 0
                recipe.total_time += recipe.cook_time
        
        return recipe
        
    except Exception as e:
        logger.error("Scraper error encountered: %s", e)
        return None


def fetch_recipe_html_safe(url: str, max_retries: int = 3) -> str:
    """
    Safely fetches HTML content from protected recipe domains like Food Network
    by fully impersonating a real browser handshake and using a linear retry backoff.
    """
    
    # Provide authentic browser header structures
    headers = {
        'Accept': 'text/html,application/xhtml+xml,'
                  'application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://google.com',
        'Upgrade-Insecure-Requests': '1',
    }

    # Implement a retry loop to handle micro-stalls or rate limits safely
    for attempt in range(max_retries):
        try:
            # Open an impersonation session block using 'chrome' 
            # handling TLS/JA3/HTTP2 fingerprinting
            with requests.Session() as session:
                response = session.get(
                    url, 
                    headers=headers, 
                    impersonate="chrome",
                    timeout=15
                )
                # Check for standard server-side HTTP errors
                response.raise_for_status()
                # Return the clean text stream layer if successful
                return response.text
                
        except RequestsError as e:
            logger.error(f"Network processing attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                # Add a brief 2-second sleep cushion before trying the fallback line again
                time.sleep(2)
            else:
                raise
