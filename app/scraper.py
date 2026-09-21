"""Web Recipe scraper utilities.
"""

import logging
import time

from curl_cffi import requests
from curl_cffi.requests.errors import RequestsError

from app.models import (
    Recipe,
    RecipeCategory,
    set_field_value,
    update_recipe_times,
    valid_fields,
)
from app.recipe_scrapers import x_scrape_html

logger = logging.getLogger(__name__)


def scrape_recipe_from_url(url) -> Recipe:
    """Fetch a remote URL and attempt to parse recipe content."""
    try:
        recipe_html = fetch_recipe_html_safe(url)        
        recipe = Recipe(source_url=url)
        try:
            scraped = x_scrape_html(recipe_html, url)
            scraper_map = {
                'image_url': 'image',
                'servings': 'yields',
            }
            category_map = {
                'SNACK': RecipeCategory.DESSERT.value,
                'SOUP': RecipeCategory.STARTER.value,
                'APPETIZER': RecipeCategory.STARTER.value,
                'CONDIMENT': RecipeCategory.COMPANION.value,
            }
            for field in valid_fields():
                func_name = scraper_map.get(field, field)
                try:
                    func = getattr(scraped, func_name, None)
                    if func and callable(func):
                        value = func()
                        if field == 'category':
                            if isinstance(value, str):
                                for cat in value.split(','):
                                    converted = cat.upper().strip()
                                    if converted in category_map:
                                        converted = category_map.get(converted)
                                    if RecipeCategory.has_value(converted):
                                        value = RecipeCategory(converted)
                                        break
                            if not RecipeCategory.has_value(value):
                                value = RecipeCategory.MAIN
                        if value:
                            set_field_value(recipe, field, value)
                except Exception as e:
                    logger.error(f"Failed to parse {field}: {e}")
        except Exception as e:
            logger.info(f"Unable to parse using 'recipe-scrapers': {e}")
        
        if not recipe.ingredients:
            raise ValueError(f'Unable to parse ingredients from {url}')
        if not recipe.instructions:
            raise ValueError(f'Unable to parse instructions from {url}')
        
        update_recipe_times(recipe)
        
        return recipe
        
    except Exception as e:
        logger.error("Scraper error encountered: %s", e)
        return None


def fetch_recipe_html_safe(url: str, max_retries: int = 3) -> str:
    """Safely fetch HTML content from protected recipe domains.
    
    Impersonates a real browser handshake and uses a linear retry backoff.
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
