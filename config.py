import os
from dotenv import load_dotenv

load_dotenv(override=True)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
WEBSITE_URL = os.getenv("WEBSITE_URL")
CACHE_DIR = "website_cache"

import os
os.makedirs(CACHE_DIR, exist_ok=True)
