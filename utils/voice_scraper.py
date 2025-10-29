# utils/build_about_async.py

import asyncio
import os
import json
import re
import time
import logging
from collections import deque
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
import httpx

from utils.url_helper import clean_html
from database.db import SessionLocal
from model.models import Firm, Website, Page, Link

# ========================================
# CONFIG
# ========================================
MAX_PAGES = 10000
CONCURRENCY = 10
TIMEOUT = 15
RETRIES = 3
BACKOFF = 0.5

logger = logging.getLogger(__name__)


# ========================================
# FETCHING UTILITIES
# ========================================
async def fetch_page(client: httpx.AsyncClient, url: str, retries: int = RETRIES, backoff: float = BACKOFF) -> str:
    """Fetch a single page asynchronously with retries."""
    for attempt in range(1, retries + 1):
        try:
            resp = await client.get(url, timeout=TIMEOUT, follow_redirects=True)
            if resp.status_code == 200 and "text/html" in resp.headers.get("content-type", ""):
                return resp.text
            return ""
        except httpx.RequestError as e:
            logger.debug(f"[FETCH] attempt {attempt} failed for {url}: {e}")
            if attempt == retries:
                logger.error(f"[ERROR] Fetch failed: {url} ({e})")
                return ""
            await asyncio.sleep(backoff * (2 ** (attempt - 1)))
        except Exception as e:
            logger.exception(f"[ERROR] Unexpected fetch error for {url}: {e}")
            return ""
    return ""


async def scrape_page(client, url, domain):
    """Fetch + parse a single page; return (page_text, links, meta info)."""
    html = await fetch_page(client, url)
    if not html:
        return "", [], {}

    soup = clean_html(html)

    # Extract main text
    texts = [e.get_text(" ", strip=True) for e in soup.find_all(["h1", "h2", "h3", "p", "li"])]
    page_text = " ".join([t for t in texts if t])

    # Extract meta
    title = soup.title.string.strip() if soup.title and soup.title.string else ""
    meta_tag = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "og:description"})
    meta_desc = meta_tag["content"].strip() if meta_tag and meta_tag.get("content") else ""

    # Extract internal links
    links = []
    for a in soup.find_all("a", href=True):
        href = urljoin(url, a["href"])
        parsed = urlparse(href)
        if parsed.netloc == domain:
            title_txt = a.get_text(strip=True) or "link"
            links.append({"title": title_txt, "url": href})

    meta_info = {"title": title, "meta_description": meta_desc}
    return page_text, links, meta_info


# ========================================
# CLEAN DOMAIN
# ========================================
def clean_domain(url: str) -> str:
    """Clean up domain for naming consistency."""
    if not url:
        return ""
    clean_url = url.replace("https://", "").replace("http://", "").replace("www.", "").rstrip("/")
    return clean_url.split(".")[0]


# ========================================
# MAIN SCRAPER FUNCTION
# ========================================
async def build_about(url: str, base_dir="scraped_data"):
    """Async concurrent scraper that crawls and stores structured data."""
    domain = urlparse(url).netloc
    visited = set()
    all_links = []
    seen_links = set()
    all_texts_by_url = {}

    q: asyncio.Queue = asyncio.Queue()
    await q.put(url)

    limits = httpx.Limits(max_connections=CONCURRENCY, max_keepalive_connections=CONCURRENCY)
    headers = {"User-Agent": "FastScraper/2.0"}

    async with httpx.AsyncClient(headers=headers, limits=limits) as client:

        async def worker():
            """Queue worker coroutine that processes pages."""
            while True:
                try:
                    current = await q.get()
                except asyncio.CancelledError:
                    break

                try:
                    if current in visited:
                        continue
                    visited.add(current)

                    page_text, links, meta_info = await scrape_page(client, current, domain)
                    if page_text:
                        all_texts_by_url[current] = {
                            "title": meta_info.get("title"),
                            "meta_description": meta_info.get("meta_description"),
                            "text": page_text
                        }

                    for link in links:
                        if link["url"] not in seen_links:
                            seen_links.add(link["url"])
                            all_links.append(link)
                        parsed = urlparse(link["url"])
                        if (
                            parsed.netloc == domain
                            and link["url"] not in visited
                            and len(visited) < MAX_PAGES
                        ):
                            await q.put(link["url"])

                except Exception as e:
                    logger.exception(f"[WORKER ERROR] {e}")
                finally:
                    try:
                        q.task_done()
                    except ValueError:
                        logger.warning(f"[WARN] task_done() double-called for {current}")

        # Spawn workers
        workers = [asyncio.create_task(worker()) for _ in range(CONCURRENCY)]

        # Wait until queue processed or max pages reached
        try:
            while len(visited) < MAX_PAGES:
                if q.empty() and q._unfinished_tasks == 0:
                    break
                await asyncio.sleep(0.1)
            await q.join()
        finally:
            for w in workers:
                if not w.done():
                    w.cancel()
            await asyncio.gather(*workers, return_exceptions=True)

    # ========================================
    # EXTRACT ABOUT DATA
    # ========================================
    first_url = next(iter(all_texts_by_url.keys()), url)
    first_data = all_texts_by_url.get(first_url, {})
    about_data = {
        "source_url": url,
        "firm_name": clean_domain(domain),
        "tagline": first_data.get("title", ""),
        "meta_description": first_data.get("meta_description", ""),
        "short_description": first_data.get("text", "")[:300],
        "full_text": " ".join([p["text"] for p in all_texts_by_url.values()]),
    }

    # ========================================
    # SAVE TO DATABASE
    # ========================================
    firm_id = save_to_db(about_data, all_links, all_texts_by_url)
    about_data["firm_id"] = firm_id
    return about_data


# ========================================
# DATABASE STORAGE
# ========================================
def save_to_db(about_obj, all_links, all_texts_by_url):
    """Store firm + website + page + link data."""
    db = SessionLocal()
    try:
        domain = urlparse(about_obj["source_url"]).netloc
        firm_name = about_obj.get("firm_name", domain)

        # === Firm ===
        firm = db.query(Firm).filter_by(name=firm_name).first()
        if not firm:
            firm = Firm(name=firm_name)
            db.add(firm)
            db.commit()
            db.refresh(firm)

        # === Website ===
        website = db.query(Website).filter_by(base_url=about_obj["source_url"]).first()
        if not website:
            website = Website(domain=domain, base_url=about_obj["source_url"], firm_id=firm.id)
            db.add(website)
            db.commit()
            db.refresh(website)

        # === Pages ===
        for page_url, content_data in all_texts_by_url.items():
            if not db.query(Page).filter_by(url=page_url).first():
                page = Page(
                    url=page_url,
                    title=content_data.get("title"),
                    meta_description=content_data.get("meta_description"),
                    content=content_data.get("text"),
                    website_id=website.id
                )
                db.add(page)

        # === Links ===
        for link in all_links:
            if not db.query(Link).filter_by(url=link["url"]).first():
                new_link = Link(
                    title=link.get("title", "link"),
                    url=link["url"],
                    website_id=website.id
                )
                db.add(new_link)

        db.commit()
        print(f"[DB] Stored {firm_name} ({domain}): {len(all_texts_by_url)} pages, {len(all_links)} links")
        return firm.id

    except Exception as e:
        db.rollback()
        print(f"[DB ERROR] {e}")
        raise
    finally:
        db.close()
