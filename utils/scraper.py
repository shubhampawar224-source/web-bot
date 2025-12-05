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
from utils.firm_manager import FirmManager

MAX_PAGES = 10000      # Limit crawl size
CONCURRENCY = 5        # Reduced from 10 to be more conservative with server resources
TIMEOUT = 10           # Reduced from 15 to fail faster on slow sites
RETRIES = 2            # Reduced from 3 to speed up processing
BACKOFF = 0.5

logger = logging.getLogger(__name__)

# Regex patterns for contact info extraction
EMAIL_PATTERN = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
PHONE_PATTERN = re.compile(r'(?:\+\d{1,3}[-.\s]?)?(?:\(?\d{1,4}\)?[-.\s]?)?\d{1,4}[-.\s]?\d{1,4}[-.\s]?\d{1,9}')

def extract_contact_info(text: str) -> dict:
    """Extract emails and phone numbers from text."""
    emails = list(set(EMAIL_PATTERN.findall(text)))
    phones = []
    
    # Find potential phone numbers
    potential_phones = PHONE_PATTERN.findall(text)
    for phone in potential_phones:
        # Clean and validate phone number (must have at least 7 digits)
        cleaned = re.sub(r'[^0-9+]', '', phone)
        if len(cleaned) >= 7:  # Minimum valid phone number length
            phones.append(phone.strip())
    
    phones = list(set(phones))[:5]  # Limit to 5 unique phone numbers
    
    return {
        "emails": emails[:10],  # Limit to 10 emails
        "phones": phones
    }


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

    # PRIORITY 1: Extract FOOTER content (hours, contact, address)
    footer_texts = []
    footer_elements = soup.find_all(['footer', 'div'], class_=lambda c: c and any(x in str(c).lower() for x in ['footer', 'contact', 'hours', 'info']))
    footer_elements += soup.find_all(['footer', 'div'], id=lambda i: i and any(x in str(i).lower() for x in ['footer', 'contact', 'hours', 'info']))
    
    for footer in footer_elements:
        footer_text = footer.get_text(" ", strip=True)
        if footer_text and len(footer_text) > 10:
            footer_texts.append(f"[FOOTER INFO] {footer_text}")
    
    # PRIORITY 2: Extract specific contact/hours elements
    contact_selectors = [
        ('time', {}),
        ('address', {}),
        ('[itemprop="openingHours"]', {}),
        ('[itemprop="telephone"]', {}),
        ('[itemprop="address"]', {}),
        ('div', {'class': lambda c: c and any(x in str(c).lower() for x in ['hours', 'schedule', 'open'])}),
        ('span', {'class': lambda c: c and any(x in str(c).lower() for x in ['phone', 'tel', 'hours'])}),
    ]
    
    contact_texts = []
    for selector, attrs in contact_selectors:
        elements = soup.find_all(selector, attrs) if attrs else soup.select(selector)
        for elem in elements:
            text = elem.get_text(" ", strip=True)
            if text and len(text) > 2:
                contact_texts.append(f"[CONTACT] {text}")
    
    # PRIORITY 3: Extract text from ALL relevant elements
    text_elements = soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "div", "span", "article", "section", "td", "th", "time", "address", "label"])
    texts = []
    for e in text_elements:
        text = e.get_text(" ", strip=True)
        # Skip empty or very short fragments, but keep them if they contain time/contact keywords
        if text and (len(text) > 3 or any(keyword in text.lower() for keyword in ['am', 'pm', 'hours', 'phone', 'email', '@'])):
            texts.append(text)
    
    # Combine: Footer first (highest priority), then contact info, then general content
    all_text = footer_texts + contact_texts + texts
    page_text = " ".join(all_text)
    
    # Extract contact information (emails and phone numbers)
    contact_data = extract_contact_info(page_text)
    
    # Add extracted contact info prominently to page text
    if contact_data["emails"]:
        page_text += " [EMAILS: " + ", ".join(contact_data["emails"]) + "]"
    if contact_data["phones"]:
        page_text += " [PHONES: " + ", ".join(contact_data["phones"]) + "]"

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
    
    # Extract ALL meta information
    meta_tag = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "og:description"})
    meta_desc = meta_tag["content"].strip() if meta_tag and meta_tag.get("content") else ""
    
    # Extract contact info from meta tags
    phone_meta = soup.find("meta", attrs={"property": "og:phone_number"}) or soup.find("meta", attrs={"name": "phone"})
    phone_info = phone_meta["content"].strip() if phone_meta and phone_meta.get("content") else ""
    
    # Extract schema.org structured data (JSON-LD)
    schema_data = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            import json
            data = json.loads(script.string)
            schema_data.append(str(data))
        except:
            pass
    
    tagline = next((t.get_text(" ", strip=True) for t in soup.find_all(["h1", "h2"]) if len(t.get_text(strip=True)) > 5), "")
    first_p = next((p.get_text(" ", strip=True) for p in soup.find_all("p") if len(p.get_text(strip=True)) > 30), "")
    
    # Append schema data and phone to full text for better searchability
    additional_info = []
    if phone_info:
        additional_info.append(f"Phone: {phone_info}")
    if schema_data:
        additional_info.append(" ".join(schema_data))

    # Combine all text with additional metadata for comprehensive search
    full_text_parts = all_texts.copy()
    if 'additional_info' in locals() and additional_info:
        full_text_parts.extend(additional_info)
    
    about_data = {
        "source_url": url,
        "firm_name": FirmManager.normalize_firm_name(url),  # Use consistent firm naming
        "tagline": tagline,
        "meta_description": meta_desc,
        "short_description": first_p,
        "full_text": " ".join(full_text_parts),
        "phone": phone_info if 'phone_info' in locals() else "",
        "has_schema_data": len(schema_data) > 0 if 'schema_data' in locals() else False
    }

    # Save to DB safely using centralized firm manager
    firm_id = save_to_db(about_data, all_links)
    about_data["firm_id"] = firm_id  # include firm_id in returned data
    about_data["full_text"]=" ".join(all_texts)

    return about_data


def save_to_db(about_obj, links_list):
    """Store firm + website data in DB and return firm_id safely."""
    db = SessionLocal()
    try:
        # Use centralized firm manager to prevent duplicates
        firm_id = FirmManager.get_or_create_firm(
            url=about_obj["source_url"],
            title=about_obj.get("firm_name"),
            db=db
        )

        # Get or create website
        website = db.query(Website).filter_by(base_url=about_obj["source_url"]).first()
        if not website:
            domain = urlparse(about_obj["source_url"]).netloc
            website = Website(domain=domain, base_url=about_obj["source_url"], firm_id=firm_id)
            db.add(website)
            db.flush()  # assign PK immediately

        # Add scraped data safely
        website.add_scraped_data(about_obj, links_list)

        db.commit()
        
        # Get firm name for logging
        firm = db.query(Firm).filter_by(id=firm_id).first()
        firm_name = firm.name if firm else "Unknown"
        print(f"[DB] Stored {firm_name} ({website.domain}) data")
        
        return firm_id
    except Exception as e:
        db.rollback()
        print(f"[DB ERROR] {e}")
        raise
    finally:
        db.close()


