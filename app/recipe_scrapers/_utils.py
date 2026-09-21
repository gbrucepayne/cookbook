"""Recipe scrapers helper utilities.
"""
import re

from bs4 import BeautifulSoup


def css_class_filter(class_list: list[str], descendant_mode: bool = True) -> str:
    """Convert a list of class strings into case-insensitive CSS selector."""
    # Loop through list, strip whitespaces, and format the CSS string fragment
    # The 'i' flag at the end forces case-insensitivity in modern CSS engines
    fragments = [f'[class*="{cls.strip()}" i]' 
                for cls in class_list if cls.strip()]
    # Space ' ' means nesting/descendants.
    # Empty string '' means compound selectors on one element.
    delimiter = ' ' if descendant_mode else ''
    return delimiter.join(fragments)


def get_list_following(heading_text: str, soup: BeautifulSoup) -> list[str]:
    """Retrieve a list of strings following a particular heading/div text."""
    list_following: list[str] = []
    tags = ['h1', 'h2', 'h3', 'h4', 'div']
    heading = soup.find(lambda tag: tag.name in tags and 
                        heading_text.strip().lower() == tag.text.strip().lower())
    if heading:
        target_list = heading.find_next(['ul', 'ol'])
        if target_list:
            list_following = []
            for li in target_list.find_all('li'):
                text = li.get_text(separator=" ", strip=True).strip()
                if text:
                    list_following.append(text)
    return list_following


def timeval_to_minutes(time_val: str) -> int:
    """Convert a text string to integer minutes."""


def recipe_time(time_val: str) -> int:
    """Derive time value in minutes from a Recipe Schema."""
    if not isinstance(time_val, str) or not time_val.strip():
        return 0
    if '&' in time_val:
        return sum([recipe_time(val.strip()) for val in time_val.split('&')])
    if ':' in time_val:
        hours, minutes = time_val.split(' ')[0].split(':', 1)
        return int(hours) * 60 + int(minutes)
    candidate = int(re.search(r'\d+', time_val).group())
    if time_val.endswith(('H', 'Hours', 'hours', 'hrs', 'Hour', 'hour')):
        return candidate * 60
    # elif time_val.endswith(('M', 'Minutes', 'minutes', 'mins', 'Minute', 'minute')):
    #     pass
    return candidate
