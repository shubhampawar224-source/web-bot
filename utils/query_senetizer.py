# utils/sanitize.py
import re

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
