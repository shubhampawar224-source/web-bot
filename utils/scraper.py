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

from utils.url_helper import clean_html  # reuse your helper
from database.db import SessionLocal
from model.models import Firm, Website

MAX_PAGES = 10000      # Limit crawl size
CONCURRENCY = 10       # Adjust based on server/network
TIMEOUT = 15           # Per-request timeout in seconds
RETRIES = 3
BACKOFF = 0.5

logger = logging.getLogger(__name__)


async def fetch_page(client: httpx.AsyncClient, url: str, retries: int = RETRIES, backoff: float = BACKOFF) -> str:
    """Fetch a single page asynchronously with retries and exponential backoff."""
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
    """Fetch + parse a single page; return (page_text, links)."""
    html = await fetch_page(client, url)
    if not html:
        return "", []

    # clean_html is expected to return a BeautifulSoup object (already sanitized)
    soup = clean_html(html)

    # Extract text
    texts = [e.get_text(" ", strip=True) for e in soup.find_all(["h1", "h2", "h3", "p", "li"])]
    page_text = " ".join([t for t in texts if t])

    # Extract internal links
    links = []
    for a in soup.find_all("a", href=True):
        href = urljoin(url, a["href"])
        parsed = urlparse(href)
        if parsed.netloc == domain:
            title = a.get_text(strip=True) or "link"
            links.append({"title": title, "url": href})

    return page_text, links

from urllib.parse import urlparse

def clean_domain(url: str, keep_subdomain: bool = False) -> str:
    """
    Remove protocol, www, and TLDs (.com, .ai, etc.) from a URL.
    If keep_subdomain=True, keeps subdomains like 'learn.deeplearning'.
    """
    if not url:
        return ""

    clean_url = url.replace("https://", "").replace("http://", "").rstrip("/")

    # Split by dots
    parts = clean_url.split(".")

    # Select first part based on length
    if len(parts) == 2:
        first_part = parts[0]
    elif len(parts) == 3:
        first_part = parts[1]
    else:
        first_part = parts[0]  # fallback

    # Last part is always last
    last_part =first_part
    # Fallback: if regex fails (like localhost or IP)
    return last_part if last_part else ""

async def build_about(url: str, base_dir="scraped_data"):
    """Async concurrent scraper using an asyncio.Queue worker-pool."""
    domain = urlparse(url).netloc
    visited = set()
    all_texts = []
    all_links = []
    seen_links = set()

    q: asyncio.Queue = asyncio.Queue()
    await q.put(url)

    limits = httpx.Limits(max_connections=CONCURRENCY, max_keepalive_connections=CONCURRENCY)
    headers = {"User-Agent": "FastScraper/1.0"}

    async with httpx.AsyncClient(headers=headers, limits=limits) as client:

        async def worker():
            """Queue worker coroutine that processes pages."""
            while True:
                try:
                    current = await q.get()
                except asyncio.CancelledError:
                    break  # exit cleanly on cancel

                try:
                    if current in visited:
                        continue  # already processed, skip without extra task_done
                    visited.add(current)

                    page_text, links = await scrape_page(client, current, domain)
                    if page_text:
                        all_texts.append(page_text)

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
                    logger.exception(f"[WORKER] error processing {current}: {e}")
                finally:
                    # Ensure task_done is only called once per q.get()
                    try:
                        q.task_done()
                    except ValueError:
                        logger.warning(f"[WARN] task_done() double-called or invalid for {current}")

        # Spawn workers
        workers = [asyncio.create_task(worker()) for _ in range(CONCURRENCY)]

        # Wait until queue processed or max pages reached
        try:
            while len(visited) < MAX_PAGES:
                if q.empty():
                    # Exit when all workers idle and queue is drained
                    if all(w.done() or w.cancelled() for w in workers):
                        break
                await asyncio.sleep(0.1)
                if q.empty() and q._unfinished_tasks == 0:
                    break
            await q.join()
        finally:
            # Clean up workers gracefully
            for w in workers:
                if not w.done():
                    w.cancel()
            await asyncio.gather(*workers, return_exceptions=True)

    # Assemble about data from collected texts
    try:
        soup = BeautifulSoup(all_texts[0] if all_texts else "", "lxml")
    except Exception:
        soup = BeautifulSoup(all_texts[0] if all_texts else "", "html.parser")

    title = soup.title.string.strip() if soup.title and soup.title.string else domain
    meta_tag = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "og:description"})
    meta_desc = meta_tag["content"].strip() if meta_tag and meta_tag.get("content") else ""
    tagline = next((t.get_text(" ", strip=True) for t in soup.find_all(["h1", "h2"]) if len(t.get_text(strip=True)) > 5), "")
    first_p = next((p.get_text(" ", strip=True) for p in soup.find_all("p") if len(p.get_text(strip=True)) > 30), "")

    about_data = {
        "source_url": url,
        "firm_name": clean_domain(title),
        "tagline": tagline,
        "meta_description": meta_desc,
        "short_description": first_p,
        "full_text": " "
    }

    # Save to DB safely
    firm_id = save_to_db(about_data, all_links)
    about_data["firm_id"] = firm_id  # include firm_id in returned data
    about_data["full_text"]=" ".join(all_texts)

    return about_data


def save_to_db(about_obj, links_list):
    """Store firm + website data in DB and return firm_id safely."""
    db = SessionLocal()
    try:
        domain = urlparse(about_obj["source_url"]).netloc
        firm_name = about_obj.get("firm_name", domain)

        # Get or create firm
        firm = db.query(Firm).filter_by(name=firm_name).first()
        if not firm:
            firm = Firm(name=firm_name)
            db.add(firm)
            db.commit()
            db.refresh(firm)  # ensures firm.id is available

        # Get or create website
        website = db.query(Website).filter_by(base_url=about_obj["source_url"]).first()
        if not website:
            website = Website(domain=domain, base_url=about_obj["source_url"], firm_id=firm.id)
            db.add(website)
            db.flush()  # assign PK immediately

        # Add scraped data safely
        website.add_scraped_data(about_obj, links_list)

        db.commit()
        print(f"[DB] Stored {firm_name} ({domain}) data")
        return firm.id
    except Exception as e:
        db.rollback()
        print(f"[DB ERROR] {e}")
        raise
    finally:
        db.close()


