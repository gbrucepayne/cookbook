"""Recipe parser for Canadian Living.
"""
import re

from recipe_scrapers import AbstractScraper
from recipe_scrapers._utils import normalize_string

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
            if sibling.name in ['p'] and sibling.get_text(strip=True):
                subheading = sibling.get_text(strip=True).replace('\n', ' ')
                if subheading == "Notes:":
                    break
                instructions.append(f"# {subheading}")
            elif sibling.name in ['ol', 'ul']:                
                for li in sibling.find_all('li'):
                    text = li.get_text(separator=" ", strip=True)
                    if '\n' in text:
                        text = ' '.join([x.strip() for x in text.split('\n')])
                    if text:
                        instructions.append(text)
        return '\n'.join(instructions)
    
    def _convert_to_minutes(self, text: str) -> int:
        pattern = r'(\d+)\s*(hour|min|hr)[a-z]*'
        matches = re.findall(pattern, text, re.IGNORECASE)
        total_minutes = 0
        for value, unit in matches:
            value = float(value)
            if any(h in unit.lower() for h in ['hour', 'hr']):
                total_minutes += value * 60
            else:
                total_minutes += value
        return int(total_minutes)
        
    def prep_time(self):
        tag = "Prep Time"
        target_th = self.soup.find(
            'th',
            string=lambda t: t and t.strip() == tag
        )
        if target_th:
            header_row = target_th.find_parent('tr')
            headers = [th.get_text(strip=True) 
                       for th in header_row.find_all('th')]
            data_row = header_row.find_next('tr')
            if data_row:
                data_values = [td.get_text(strip=True) 
                               for td in data_row.find_all('td')]
                prep_time_str = data_values[headers.index(tag)]
                prep_time = self._convert_to_minutes(prep_time_str)
                if prep_time:
                    return prep_time
        raise ValueError("Unable to derive Prep Time")
    
    def cook_time(self):
        tag = "Cook Time"
        target_th = self.soup.find(
            'th',
            string=lambda t: t and t.strip() == tag
        )
        if target_th:
            header_row = target_th.find_parent('tr')
            headers = [th.get_text(strip=True) 
                       for th in header_row.find_all('th')]
            data_row = header_row.find_next('tr')
            if data_row:
                data_values = [td.get_text(strip=True) 
                               for td in data_row.find_all('td')]
                cook_time_str = data_values[headers.index(tag)]
                cook_time = self._convert_to_minutes(cook_time_str)
                if cook_time:
                    return cook_time
        raise ValueError("Unable to derive Cook Time")
    
    def yields(self):
        tag = "Portions"
        target_th = self.soup.find(
            'th',
            string=lambda t: t and t.strip() == tag
        )
        if target_th:
            header_row = target_th.find_parent('tr')
            headers = [th.get_text(strip=True) 
                       for th in header_row.find_all('th')]
            data_row = header_row.find_next('tr')
            if data_row:
                data_values = [td.get_text(strip=True) 
                               for td in data_row.find_all('td')]
                idx = headers.index(tag)
                portions = data_values[idx]
                match = re.search(r'\d+(?:-\d+)?', portions)
                if match:
                    portion_size = match.group(0).split('-')[0]
                    return int(portion_size)
        raise ValueError("Unable to derive yields (Portions)")
    
    def description(self):
        target = self.soup.find('h2', {'class': 'b-subheadline'})
        if target:
            return target.get_text(strip=True)
        raise ValueError("Unable to derive description (subheadline)")
    
    def notes(self):
        tag = "Notes:"
        target = self.soup.find('b', string=lambda t: t and t.strip() == tag)
        if target:
            notes: list[str] = []
            parent_p = target.find_parent('p')
            if parent_p:
                for sibling in parent_p.next_siblings:
                    if sibling.name in ['p'] and sibling.get_text(strip=True):
                        notes.append(sibling.get_text(strip=True))
            if notes:
                return notes
        raise ValueError("Unable to derive Notes")
