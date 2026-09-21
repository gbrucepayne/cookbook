"""Generic Scraper class for deriving from unsupported sites.
"""
import json
import logging
import re
from enum import Enum
from typing import Any

from bs4 import BeautifulSoup
from recipe_scrapers import AbstractScraper

from ._utils import css_class_filter, get_list_following, recipe_time

logger = logging.getLogger(__name__)


class TimeType(Enum):
    PREP = "prep"
    COOK = "cook"
    TOTAL = "total"


class GenericScraper(AbstractScraper):
    
    def __init__(self, html, url, best_image = None):
        try:
            super().__init__(html, url, best_image)
        except Exception as e:
            logger.error(e)
        if not self.page_data:
            self.page_data = html
        if not isinstance(self.soup, BeautifulSoup):
            self.soup = BeautifulSoup(self.page_data, "html.parser")
        self._get_schema()
    
    def _get_schema(self):
        schema_tags = self.soup.find_all('script', type='application/ld+json')
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
                        self.schema = schema
                        break
            except Exception as e:
                logger.error(e)
                continue
        if not isinstance(self.schema, dict):
            self.schema = None
        
    @classmethod
    def host(cls):
        return "ANY"
    
    def title(self):
        title_el = self.soup.find('meta', 'og:title') or self.soup.find('h1')
        if title_el:
            if title_el.has_attr('content'):
                return title_el['content']
            return title_el.get_text().strip()
        raise ValueError("Title not found")
    
    def author(self):
        author_el = self.soup.find('meta', 'og:author')
        if author_el and author_el.has_attr('content'):
            return author_el['content']
        raise ValueError("Author not found")
    
    def site_name(self):
        site_el = self.soup.find('meta', 'og:site_name')
        if site_el and site_el.has_attr('content'):
            return site_el['content']
        raise ValueError("Title not found")
    
    def category(self):
        return "MAIN"
    
    def description(self):
        desc_meta = self.soup.find('meta', property='og:description')
        if desc_meta and isinstance(desc_meta.attrs, dict):
            return desc_meta.attrs.get('content')
    
    def _extract_recipe_time(self, time_type = TimeType.TOTAL) -> int|None:
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
        if isinstance(self.schema, dict):
            for tag in tags:
                candidate = self.schema.get(tag)
                if candidate:
                    timeval = recipe_time(candidate)
                    break
        if not timeval:
            for el in self.soup.select(css_class_filter(classes)):
                candidate = el.text.strip()
                if candidate:
                    timeval = recipe_time(candidate)
                    break
        return timeval

    def total_time(self):
        return self._extract_recipe_time(TimeType.TOTAL)
    
    def prep_time(self):
        return self._extract_recipe_time(TimeType.PREP)
    
    def cook_time(self):
        return self._extract_recipe_time(TimeType.COOK)
    
    def image(self):
        return super().image()
    
    def ingredients(self):
        ingredients: list[str] = []
        # Recipe Schema
        if isinstance(self.schema, dict):
            tags = ['recipeIngredient']
            for tag in tags:
                candidate = self.schema.get(tag)
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
        if not ingredients:
            ingredients = get_list_following('Ingredients')
            if not ingredients:
                classes = ['ingredient', 'recipe-ing', 'wprm-recipe-ingredient']
                section_headers = ('ingredients',)
                for el in self.soup.select(css_class_filter(classes)):
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
    
    def instructions(self):
        instructions: list[str] = []
        # Recipe Schema
        if isinstance(self.schema, dict):
            tags = ['recipeInstructions']
            for tag in tags:
                candidate = self.schema.get(tag)
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
        if not instructions:
            headings = ['Instructions', 'Method']
            for heading in headings:
                instructions = get_list_following(heading)
                if instructions: break
            if not instructions:
                classes = ['instruction', 'step', 'direction', 
                        'wprm-recipe-instruction', 'preparation']
                headers = ('instructions', 'method',)
                step_number_pattern = r'^\s*\d+(?!\s*[\/\.])[\s\.\-\–\—:]*'
                for el in self.soup.select(css_class_filter(classes)):
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
    
    def yields(self):
        return super().yields()
