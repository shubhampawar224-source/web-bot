import os
import time
from urllib.parse import urlparse
from utils.scraper import scrape_website
from config import CACHE_DIR

def get_cache_file(url: str) -> str:
    domain = urlparse(url).netloc.replace(":", "_")
    return os.path.join(CACHE_DIR, f"{domain}.txt")

def is_cache_stale(file: str, max_age: int = 186400) -> bool:
    if not os.path.exists(file):
        return True
    return (time.time() - os.path.getmtime(file)) > max_age

def load_website_text(url: str) -> str:
    cache_file = get_cache_file(url)

    if is_cache_stale(cache_file):
        print(f"[Info] Cache stale or missing. Scraping {url}...")
        website_text = scrape_website(url)
        with open(cache_file, "w", encoding="utf-8") as f:
            f.write(website_text)
    else:
        print(f"[Info] Loading cached website content from {cache_file}")
        with open(cache_file, "r", encoding="utf-8") as f:
            website_text = f.read()

    return website_text
