"""Recipe parser for Canadian Living.
"""
from recipe_scrapers import AbstractScraper
from recipe_scrapers._utils import normalize_string

from app.recipe_scrapers._utils import recipe_time


class CanadianLiving(AbstractScraper):
    @classmethod
    def host(cls, domain="com"):
        return f"canadianliving.{domain}"
    
    def title(self):
        title_el = self.soup.find('meta', 'og:title') or self.soup.find('h1')
        if title_el:
            if title_el.has_attr('content'):
                return title_el['content']
            return normalize_string(title_el.get_text().strip())
        raise ValueError("Title not found")
    
    def author(self):
        author_el = self.soup.find('meta', 'og:article:author')
        if author_el and author_el.has_attr('content'):
            return author_el['content']
        raise ValueError("Author not found")
    
    def site_name(self):
        site_el = self.soup.find('meta', 'og:site_name')
        if site_el and site_el.has_attr('content'):
            return site_el['content']
        raise ValueError("Title not found")
    
    def category(self):
        meta_tag = self.soup.find('meta', attrs={
            'name': 'cXenseParse:recs:category',
        })
        if meta_tag and meta_tag.has_attr('content'):
            cat = meta_tag.get('content').lower()
            if cat.endswith(('lunch', 'dinner', 'breakfast')):
                return "MAIN"
        return "MAIN"

    def ingredients(self):
        ingredients = []
        heading_text = "Ingredients"
        tags = ['h4']
        heading = self.soup.find(lambda tag: tag.name in tags and 
                                 heading_text == tag.text.strip())
        if not heading:
            raise ValueError("Unable find Ingredients section")
        target_list = heading.find_next(['ul'])
        if not target_list:
            raise ValueError("Unable to find Ingredients list")
        for li in target_list.find_all('li'):
            text = li.get_text(separator=" ", strip=True)
            if '\n' in text:
                text = ' '.join([x.strip() for x in text.split('\n')])
            if text:
                ingredients.append(text)
        return ingredients
    
    def instructions(self):
        instructions = []
        heading_text = "Method"
        tags = ['h4']
        heading = self.soup.find(lambda tag: tag.name in tags and 
                                 heading_text == tag.text.strip())
        if not heading:
            raise ValueError("Unable find Method section")
        enclosing_div = heading.find_parent('section')
        if enclosing_div:
            paragraphs = enclosing_div.find_all('p')
            for p in paragraphs:
                instructions.append(p.get_text(strip=True))
        return '\n'.join(instructions)
    
    def prep_time(self):
        target_span = self.soup.find('span', string="Prep time")
        if target_span:
            next_span = target_span.find_next('span')
            if next_span:
                return recipe_time(next_span.get_text())
        raise ValueError("Unable to derive prep time")
    
    def total_time(self):
        target_span = self.soup.find('span', string="Total time")
        if target_span:
            next_span = target_span.find_next('span')
            if next_span:
                return recipe_time(next_span.get_text())
        raise ValueError("Unable to derive total time")
    
    def yields(self):
        target_span = self.soup.find('span', string="Portion size")
        if target_span:
            next_span = target_span.find_next('span')
            if next_span:
                portion_size = next_span.get_text()
                return int(portion_size.split(' ')[0])
        raise ValueError("Unable to derive yields")
    
    def nutrients(self):
        target_div = self.soup.find('div', attrs={
            'class': 'nutritional-values',
        })
        if target_div:
            nutrition_list = target_div.find_next('ul')
            if nutrition_list:
                return ' | '.join([li.get_text(separator=': ', strip=True) 
                                   for li in nutrition_list.find_all('li')])
        raise ValueError("Unable to derive nutrients")
