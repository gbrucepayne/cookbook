import json
import logging
import re
from typing import Any

import requests
from bs4 import BeautifulSoup

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
    return ingredients_list  


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


def _recipe_schema_time(time_val: str) -> int|None:
    """Derive time value in minutes from a Recipe Schema."""
    if isinstance(time_val, str) and time_val:
        candidate = int(re.search(r'\d+', time_val).group())
        if time_val.endswith(('M', 'Minutes')):
            return candidate
    return None


def extract_prep_time(meta: dict[str, Any]|BeautifulSoup) -> int|None:
    """Extract preparation time."""
    prep_time = None
    if isinstance(meta, dict):
        tags = ['prepTime']
        for tag in tags:
            candidate = meta.get(tag)
            if candidate:
                prep_time = _recipe_schema_time(candidate)
                break
    if not prep_time and isinstance(meta, BeautifulSoup):
        classes = ['wprm-recipe-prep_time-minutes']
        for el in meta.select(_css_class_filter(classes)):
            candidate = el.text.strip()
            if candidate:
                prep_time = int(re.search(r'\d+', candidate).group())
                break
    return prep_time


def extract_cook_time(meta: dict[str, Any]|BeautifulSoup) -> int|None:
    """Extract cook time."""
    cook_time = None
    if isinstance(meta, dict):
        tags = ['cookTime']
        for tag in tags:
            candidate = meta.get(tag)
            if candidate:
                cook_time = _recipe_schema_time(candidate)
                break
    if not cook_time and isinstance(meta, BeautifulSoup):
        classes = ['wprm-recipe-cook_time-minutes']
        for el in meta.select(_css_class_filter(classes)):
            candidate = el.text.strip()
            if candidate:
                cook_time = int(re.search(r'\d+', candidate).group())
                break
    return cook_time


def extract_total_time(meta: dict[str, Any]|BeautifulSoup) -> int|None:
    """Extract total time."""
    total_time = None
    if isinstance(meta, dict):
        tags = ['totalTime']
        for tag in tags:
            candidate = meta.get(tag)
            if candidate:
                total_time = _recipe_schema_time(candidate)
                break
    if not total_time and isinstance(meta, BeautifulSoup):
        classes = ['wprm-recipe-total_time-minutes']
        for el in meta.select(_css_class_filter(classes)):
            candidate = el.text.strip()
            if candidate:
                total_time = int(re.search(r'\d+', candidate).group())
                break
    return total_time


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
                        prep_time = extract_prep_time(schema)
                        cook_time = extract_cook_time(schema)
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
            prep_time = extract_prep_time(soup)
        if not cook_time:
            cook_time = extract_cook_time(soup)
        
        # # Select common recipe schema target classes
        # for item in soup.find_all(['li', 'span', 'p', 'div']):
        #     classes = ' '.join(item.get('class', [])).lower()
        #     candidate = item.text.strip()
        #     if not candidate:
        #         continue
            
        #     if '\n' in candidate:
        #         candidate = '\n'.join([c.strip() for c in candidate.split('\n') if c.strip()])
                
        #     if any(x in classes for x in ['ingredient', 'recipe-ing', 'wprm-recipe-ingredient']):
        #         if candidate.lower() not in ['ingredients']:
        #             ingredients_list.append(candidate)
            
        #     elif any(x in classes for x in ['instruction', 'step', 'direction', 'wprm-recipe-instruction', 'preparation']):
        #         if candidate.lower() not in ['instructions', 'directions', 'preparation']:
        #             instructions_list.append(candidate)
            
        #     elif any(x in classes for x in ['wprm-recipe-servings']):
        #         if item.name == 'input' or item.has_attr('value'):
        #             servings = item.get('value', '').strip()
        #         elif item.has_attr('data-servings'):
        #             servings = item.get('data-servings', '').strip()
        #         else:
        #             servings = candidate
        #         servings = int(re.search(r'\d+', servings).group())
                
        #     elif any(x in classes for x in ['wprm-recipe-prep_time-minutes']):
        #         prep_time = int(re.search(r'\d+', candidate).group())
                
        #     elif any(x in classes for x in ['wprm-recipe-cook_time-minutes']):
        #         cook_time = int(re.search(r'\d+', candidate).group())
                
        # for item in soup.find_all(['li', 'p', 'div']):
        #     classes = ' '.join(item.get('class', [])).lower()
        #     if any(x in classes for x in ['instruction', 'step', 'direction', 'wprm-recipe-instruction']):
        #         if item.text.strip():
        #             instructions_list.append(item.text.strip())
                
        # servings_el = soup.select_one('[class*="wprm-recipe-servings"]')
        # if servings_el:
        #     if servings_el.name == 'input' or servings_el.has_attr('value'):
        #         servings = servings_el.get('value', '').strip()
        #     elif servings_el.has_attr('data-servings'):
        #         servings = servings_el.get('data-servings', '').strip()
        #     else:
        #         servings = servings_el.text.strip()
        #     servings = int(re.search(r'\d+', servings).group())
        
        # prep_el = soup.select_one('[class*="wprm-recipe-prep_time-minutes"]')
        # prep_time = int(re.search(r'\d+', prep_el.text.strip()).group()) if prep_el else None
        
        # cook_el = soup.select_one('[class*="wprm-recipe-cook_time-minutes"]')
        # cook_time = int(re.search(r'\d+', cook_el.text.strip()).group()) if cook_el else None

        # # Fallbacks for generic markup structures
        # if not ingredients_list:
        #     ingredients_list = [el.text.strip() for el in soup.select('[class*="ingredient" i]') if el.text.strip()]
        # if not instructions_list:
        #     instructions_list = [el.text.strip() for el in soup.select('[class*="step" i], [class*="instruction" i]') if el.text.strip()]

        # Clean duplicates up to a reasonable cap
        ingredients = '\n'.join(list(dict.fromkeys(ingredients_list))[:40])
        instructions = '\n'.join(list(dict.fromkeys(instructions_list))[:40])

        if not ingredients: ingredients = "Auto-parsing fell short. Please edit ingredients manually."
        if not instructions: instructions = "Auto-parsing fell short. Please edit instructions manually."

        return {
            "title": title,
            "description": description,
            "ingredients": ingredients,
            "instructions": instructions,
            "image_url": image_url,
            "servings": servings,
            "prep_time": prep_time,
            "cook_time": cook_time,
        }
    except Exception as e:
        logger.error("Scraper error encountered: %s", e)
        return None
