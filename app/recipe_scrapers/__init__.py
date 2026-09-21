import importlib.util
import inspect
import logging
from pathlib import Path
from urllib.parse import urlparse

from recipe_scrapers import AbstractScraper, scrape_html

from ._generic import GenericScraper

logger = logging.getLogger(__name__)


def find_class_by_host(target_host: str) -> AbstractScraper:
    ignore = ['__init__.py', '_utils.py', '_generic.py']
    folder = Path('./app/recipe_scrapers')
    for file_path in folder.glob('*.py'):
        if file_path.name in ignore:
            continue
        module_name = file_path.stem
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for _name, cls in inspect.getmembers(module, inspect.isclass):
            if cls.__module__ == module_name:
                if hasattr(cls, 'host') and inspect.ismethod(cls.host):
                    try:
                        if cls.host() == target_host:
                            logger.info("Parsed from %s using %s",
                                        target_host, file_path.name)
                            return cls
                    except Exception as e:
                        logger.error(e)
                        continue
        logger.info("Parsed from %s using raw HTML", target_host)
        return GenericScraper


def x_scrape_html(html: str|None,
                  org_url: str,
                  best_image: bool|None = None,
                  ) -> AbstractScraper:
    """Extends the `recipe-scrapers` method for custom/generic parsing."""
    try:
        scraped = scrape_html(html, org_url, best_image=best_image)
        logger.info("Standard recipe-scrapers parsed %s", org_url)
        return scraped
    except Exception as e:
        logger.debug(str(e).replace('\n', ' '))
    parsed_url = urlparse(org_url)
    domain_name = parsed_url.netloc.lower().replace('www.', '')
    scraper_cls = find_class_by_host(domain_name)
    if scraper_cls and issubclass(scraper_cls, AbstractScraper):
        return scraper_cls(html, org_url, best_image=best_image)
    raise NotImplementedError("Unable to derive scraper")
