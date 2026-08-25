import json
import logging
import re

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


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
        
        soup = BeautifulSoup(response.content, 'html.parser')
        title_el = soup.find('h1')
        title = title_el.text.strip() if title_el else soup.find('meta', 'og:title')
        if not title:
            title = f"Imported Web Recipe ({url})"
        desc_meta = soup.find('meta', property='og:description')
        description = desc_meta.attrs.get('content') if desc_meta and isinstance(desc_meta.attrs, dict) else None
        
        image_url = None
        schema_tags = soup.find_all('script', type='application/ld+json')
        for tag in schema_tags:
            try:
                if not tag.string:
                    continue
                data = json.loads(tag.string)
                # JSON-LD can be a single dictionary or a list of schemas
                schemas = data if isinstance(data, list) else [data]
                if isinstance(data, dict) and '@graph' in data:
                    schemas = data['@graph']
                
                for schema in schemas:
                    # Look for explicit Recipe objects or graphs containing image arrays
                    if schema.get('@type') == 'Recipe' or 'Recipe' in schema.get('@graph', []):
                        recipe_node = schema if schema.get('@type') == 'Recipe' else next(node for node in schema['@graph'] if node['@type'] == 'Recipe')
                        
                        img_data = recipe_node.get('image')
                        if isinstance(img_data, list) and img_data:
                            image_url = img_data[0]
                        elif isinstance(img_data, dict):
                            image_url = img_data.get('url')
                        elif isinstance(img_data, str):
                            image_url = img_data
                        break
                if image_url:
                    break
            except Exception as e:
                logger.error(e)
                continue
        if not image_url:
            og_image = soup.find('meta', property='og:image')
            if og_image and og_image.get('content'):
                image_url = og_image['content']
            else:
                # Fallback to the first large structural layout image within the content body
                img_tag = soup.find('img', class_=lambda c: c and any(x in c.lower() for x in ['hero', 'recipe', 'wp-post-image']))
                if img_tag and img_tag.get('src'):
                    image_url = img_tag['src']
        
        ingredients_list = []
        instructions_list = []
        
        # Select common recipe schema target classes
        for item in soup.find_all(['li', 'span', 'p']):
            classes = ' '.join(item.get('class', [])).lower()
            if any(x in classes for x in ['ingredient', 'recipe-ing', 'wprm-recipe-ingredient']):
                ingredients_list.append(item.text.strip())
                
        for item in soup.find_all(['li', 'p', 'div']):
            classes = ' '.join(item.get('class', [])).lower()
            if any(x in classes for x in ['instruction', 'step', 'direction', 'wprm-recipe-instruction']):
                instructions_list.append(item.text.strip())
                
        # wprm-recipe-prep-time-minutes
        # wprm-recipe-cook-time-minutes
        # wprm-recipe-servings
        servings = prep_time = cook_time = None
        servings_el = soup.select_one('[class*="wprm-recipe-servings"]')
        if servings_el:
            if servings_el.name == 'input' or servings_el.has_attr('value'):
                servings = servings_el.get('value', '').strip()
            elif servings_el.has_attr('data-servings'):
                servings = servings_el.get('data-servings', '').strip()
            else:
                servings = servings_el.text.strip()
            servings = int(re.search(r'\d+', servings).group())
        
        prep_el = soup.select_one('[class*="wprm-recipe-prep_time-minutes"]')
        prep_time = int(re.search(r'\d+', prep_el.text.strip()).group()) if prep_el else None
        
        cook_el = soup.select_one('[class*="wprm-recipe-cook_time-minutes"]')
        cook_time = int(re.search(r'\d+', cook_el.text.strip()).group()) if cook_el else None
        

        # Fallbacks for generic markup structures
        if not ingredients_list:
            ingredients_list = [el.text.strip() for el in soup.select('[class*="ingredient" i]') if el.text.strip()]
        if not instructions_list:
            instructions_list = [el.text.strip() for el in soup.select('[class*="step" i], [class*="instruction" i]') if el.text.strip()]

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
