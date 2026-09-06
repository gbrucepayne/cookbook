"""Web Recipe scraper utilities.
"""

import json
import logging
import re
from enum import Enum
from typing import Any

import requests
from bs4 import BeautifulSoup

from .ingredient import scale_ingredient_line

logger = logging.getLogger(__name__)


def _css_class_filter(class_list: list[str], descendant_mode: bool = True) -> str:
    """
    Takes a list of class strings and turns them into a case-insensitive 
    CSS substring selector string.
    """
    # Loop through list, strip whitespaces, and format the CSS string fragment
    # The 'i' flag at the end forces case-insensitivity in modern CSS engines
    fragments = [f'[class*="{cls.strip()}" i]' for cls in class_list if cls.strip()]
    # Space ' ' means nesting/descendants. Empty string '' means compound selectors on one element.
    delimiter = ' ' if descendant_mode else ''
    return delimiter.join(fragments)


def extract_image_url(meta: dict[str, Any]|BeautifulSoup) -> str|None:
    """Extract the recipe image link."""
    image_url = None
    if isinstance(meta, dict):
        img_data = meta.get('image')
        if isinstance(img_data, list) and img_data:
            image_url = img_data[0]
        elif isinstance(img_data, dict):
            image_url = img_data.get('url')
        elif isinstance(img_data, str):
            image_url = img_data
    if not image_url and isinstance(meta, BeautifulSoup):
        og_image = meta.find('meta', property='og:image')
        if og_image and og_image.get('content'):
            image_url = og_image['content']
        else:
            # Fallback to the first large structural layout image within the content body
            img_tags = ['hero', 'recipe', 'wp-post-image']
            img_tag = meta.find('img', class_=lambda c: c and any(x in c.lower() for x in img_tags))
            if img_tag and img_tag.get('src'):
                image_url = img_tag['src']
    return image_url


def extract_ingredients(meta: dict[str, Any]|BeautifulSoup) -> list[str]:
    """Extract ingredients from a candidate text string/block."""
    ingredients_list: list[str] = []
    if isinstance(meta, dict):
        tags = ['recipeIngredient']
        for tag in tags:
            candidate = meta.get(tag)
            if not candidate:
                continue
            if isinstance(candidate, list):
                ingredients_list = list(dict.fromkeys(ingredients_list + candidate))
            elif isinstance(candidate, str) and candidate not in ingredients_list:
                ingredients_list.append(candidate)
            break
    if not ingredients_list and isinstance(meta, BeautifulSoup):
        classes = ['ingredient', 'recipe-ing', 'wprm-recipe-ingredient']
        section_headers = ('ingredients',)
        for el in meta.select(_css_class_filter(classes)):
            candidate = el.text.strip()
            if '\n' in candidate:
                for i, c in enumerate(candidate.split('\n')):
                    item = c.strip()
                    if (item and 
                        not (i == 1 and item.lower().startswith(section_headers)) and
                        item not in ingredients_list):
                        # Add item
                        ingredients_list.append(item)
            elif candidate and candidate not in ingredients_list:
                ingredients_list.append(candidate)
    formatted = [scale_ingredient_line(i) for i in ingredients_list]
    return formatted


def extract_instructions(meta: dict[str, Any]|BeautifulSoup) -> list[str]:
    """Extract instructions from a candidate text string/block."""
    instructions_list: list[str] = []
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
                                raise ValueError(f"Unexpected structure: {candidate}")
                        elif item_type in ['HowToStep']:
                            item_list.append(item)
                    candidate = [step.get('text') for step in item_list if step.get('text')]
                else:
                    raise ValueError(f"Unexpected structure: {candidate}")
            elif isinstance(candidate, str):
                candidate = [i.strip() for i in candidate.split('\n') if i.strip()]
            instructions_list = list(dict.fromkeys(instructions_list + candidate))
            break
    if not instructions_list and isinstance(meta, BeautifulSoup):
        classes = ['instruction', 'step', 'direction', 'wprm-recipe-instruction', 'preparation']
        section_headers = ('instructions',)
        step_number_pattern = r'^\s*\d+(?!\s*[\/\.])[\s\.\-\–\—:]*'
        for el in meta.select(_css_class_filter(classes)):
            candidate = el.text.strip()
            if '\n' in candidate:
                for i, c in enumerate(candidate.split('\n')):
                    item = c.strip()
                    if (item and 
                        not (i == 1 and item.lower().startswith(section_headers)) and
                        item not in instructions_list):
                        # Add item
                        instructions_list.append(re.sub(step_number_pattern, '', item))
            elif candidate and candidate not in instructions_list:
                instructions_list.append(re.sub(step_number_pattern, '', candidate))
    return instructions_list  


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


def extract_recipe_time(meta: dict[str, Any]|BeautifulSoup, time_type = TimeType.TOTAL) -> int|None:
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


def scrape_recipe_from_url(url):
    """
    Fetches a remote URL and attempts to parse recipe content.
    Returns a dictionary of extracted fields, or None if it completely fails.
    """
    try:
        # Create an active network session to retain secure cookies 
        # (This mimics how standard browsers handle handshake policies)
        session = requests.Session()
        # Comprehensive browser fingerprint spoofing configurations
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate',
            'Referer': 'https://google.com',   # Makes it look like user clicked a Google link
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
        }
        response = session.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        ingredients_list = []
        instructions_list = []
        image_url = None
        servings = None
        prep_time = None
        cook_time = None
        total_time = None
        
        soup = BeautifulSoup(response.content, 'html.parser')
        title_el = soup.find('h1')
        title = title_el.text.strip() if title_el else soup.find('meta', 'og:title')
        if not title:
            title = f"Imported Web Recipe ({url})"
        desc_meta = soup.find('meta', property='og:description')
        description = desc_meta.attrs.get('content') if desc_meta and isinstance(desc_meta.attrs, dict) else None
        
        schema_tags = soup.find_all('script', type='application/ld+json')
        for tag in schema_tags:
            try:
                if not tag.string:
                    continue
                data = json.loads(tag.string)
                # JSON-LD can be a single dictionary or a list of schemas
                schemas = data if isinstance(data, list) else [data]
                if isinstance(data, dict) and isinstance(data.get('@graph'), list):
                    graph = data.get('@graph')
                    if (all(isinstance(x, dict) for x in graph) and
                        any(x.get('@type') == 'Recipe' for x in graph)):
                        schemas = data['@graph']
                for schema in schemas:
                    # Look for explicit Recipe objects
                    if schema.get('@type') == 'Recipe':
                        ingredients_list = extract_ingredients(schema)
                        instructions_list = extract_instructions(schema)
                        image_url = extract_image_url(schema)
                        servings = extract_servings(schema)
                        prep_time = extract_recipe_time(schema, TimeType.PREP)
                        cook_time = extract_recipe_time(schema, TimeType.COOK)
                        total_time = extract_recipe_time(schema, TimeType.TOTAL)
                        break
            except Exception as e:
                logger.error(e)
                continue
        
        if not ingredients_list:
            ingredients_list = extract_ingredients(soup)
        if not instructions_list:
            instructions_list = extract_instructions(soup)
        if not image_url:
            image_url = extract_image_url(soup)
        if not servings:
            servings = extract_servings(soup)
        if not prep_time:
            prep_time = extract_recipe_time(soup, TimeType.PREP)
        if not cook_time:
            cook_time = extract_recipe_time(soup, TimeType.COOK)
        if not total_time:
            total_time = extract_recipe_time(soup, TimeType.TOTAL)
        
        # Clean duplicates up to a reasonable cap
        ingredients = '\n'.join(list(dict.fromkeys(ingredients_list))[:40])
        instructions = '\n'.join(list(dict.fromkeys(instructions_list))[:40])

        if not ingredients: ingredients = "Auto-parsing fell short. Please edit ingredients manually."
        if not instructions: instructions = "Auto-parsing fell short. Please edit instructions manually."

        if not total_time and (prep_time or cook_time):
            if prep_time:
                total_time = prep_time
            if cook_time:
                if not total_time:
                    total_time = 0
                total_time += cook_time
        
        return {
            "title": title,
            "description": description,
            "ingredients": ingredients,
            "instructions": instructions,
            "image_url": image_url,
            "servings": servings,
            "prep_time": prep_time,
            "cook_time": cook_time,
            "total_time": total_time,
        }
        
    except Exception as e:
        logger.error("Scraper error encountered: %s", e)
        return None
