# utils/sanitize.py
import re
from sqlalchemy.orm import Session

BLOCKED_PATTERNS = [
    r"\b(drop|delete|truncate|update|insert|alter|shutdown|exec|system)\b",
    r";", r"--", r"/\*", r"\*/"
]

def is_safe_query(query: str) -> bool:
    q = query.lower()
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, q):
            return False
    return True


def get_firm_name_for_url(url: str, db: Session) -> str:
    """Helper function to get firm name for a URL"""
    try:
        # Check if this URL has an associated website and firm
        website = db.query(Website).filter(Website.base_url == url).first()
        if website and website.firm:
            return website.firm.name
        else:
            # Try to get firm name from URL using firm manager
            return FirmManager.normalize_firm_name(url)
    except Exception as e:
        print(f"⚠️ Could not get firm info for URL {url}: {e}")
        return "Unknown"

