"""Recipe parser for Canadian Living.
"""
from recipe_scrapers import AbstractScraper
from recipe_scrapers._utils import normalize_string

from app.recipe_scrapers._utils import recipe_time

URL_BASE_PATH = 'more.ctv.ca/shows/the-good-stuff-with-mary-berg/recipes'


class MaryBergGoodStuff(AbstractScraper):
    @classmethod
    def host(cls):
        return "more.ctv.ca"
    
    @classmethod
    def valid_url(cls, url: str) -> bool:
        return URL_BASE_PATH in url
    
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
        site_el = self.soup.find('meta', 'og:url')
        if site_el and site_el.has_attr('content'):
            content = site_el['content'] or ''
            if 'good-stuff-with-mary-berg' in content:
                return "The Good Stuff with Mary Berg"
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
        next_sect_text = "Directions"
        tags = ['h2']
        heading = self.soup.find(lambda tag: tag.name in tags and 
                                 heading_text == tag.text.strip())
        if not heading:
            raise ValueError(f"Unable find {heading_text} section")
        for sibling in heading.next_siblings:
            if sibling.name is None:
                continue
            if sibling.name in tags and next_sect_text in sibling.text.strip():
                break
            if sibling.name in ['p'] and sibling.text.strip():
                subheading = sibling.text.strip().replace('\n', ' ')
                ingredients.append(f"# {subheading}")
            elif sibling.name in ['ul', 'ol']:                
                for li in sibling.find_all('li'):
                    text = li.get_text(separator=" ", strip=True)
                    if '\n' in text:
                        text = ' '.join([x.strip() for x in text.split('\n')])
                    if text:
                        ingredients.append(text)
        return ingredients
    
    def instructions(self):
        instructions = []
        heading_text = "Directions"
        tags = ['h2']
        heading = self.soup.find(lambda tag: tag.name in tags and 
                                 heading_text == tag.text.strip())
        if not heading:
            raise ValueError(f"Unable find {heading_text} section")
        for sibling in heading.next_siblings:
            if sibling.name is None:
                continue
            if sibling.name in ['p'] and sibling.text.strip():
                subheading = sibling.text.strip().replace('\n', ' ')
                instructions.append(f"# {subheading}")
            elif sibling.name in ['ol', 'ul']:                
                for li in sibling.find_all('li'):
                    text = li.get_text(separator=" ", strip=True)
                    if '\n' in text:
                        text = ' '.join([x.strip() for x in text.split('\n')])
                    if text:
                        instructions.append(text)
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
        target_table = self.soup.find('th', string="Portions")
        if target_table:
            next_row = target_table.find_next('td')
            if next_row:
                portion_size = next_row.get_text().split(' ')[1]
                if '-' in portion_size:
                    portion_size = portion_size.split('-')[0].strip()
                return int(portion_size)
        raise ValueError("Unable to derive yields")
