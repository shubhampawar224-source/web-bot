import os
from dotenv import load_dotenv

load_dotenv(override=True)

# API Keys
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
CARTESIA_API_KEY = os.getenv("CARTESIA_API_KEY")

# LiveKit Configuration
LIVEKIT_URL = os.getenv("LIVEKIT_URL")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET")

# Database Configuration
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./kitkool_bot.db")
DATABASE_URI = os.getenv("DATABASE_URI", "sqlite:///scraped_data.db")

# Admin & Security Configuration
SECRET_KEY = os.getenv("SECRET_KEY", "your-fallback-secret-key")
APP_NAME = os.getenv("APP_NAME", "KitKool Web Bot")
ADMIN_SESSION_EXPIRE_HOURS = int(os.getenv("ADMIN_SESSION_EXPIRE_HOURS", "24"))
DEFAULT_ADMIN_USERNAME = os.getenv("DEFAULT_ADMIN_USERNAME", "admin")
DEFAULT_ADMIN_PASSWORD = os.getenv("DEFAULT_ADMIN_PASSWORD", "admin123")

# Google OAuth Configuration
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")

# Email Configuration
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
FROM_EMAIL = os.getenv("FROM_EMAIL")
TO_EMAIL = os.getenv("TO_EMAIL")

# Application Configuration
WEBSITE_URL = os.getenv("WEBSITE_URL")
WIDGET_BASE_URL = os.getenv("WIDGET_BASE_URL", "http://127.0.0.1:8000/")
CACHE_DIR = "website_cache"
CHROMA_PERSIST_DIRECTORY = os.getenv("CHROMA_PERSIST_DIRECTORY", "./rag_db")

# Model Configuration
MODEL_NAME = os.getenv("Model_name", "gpt-4o")

# Create cache directory
os.makedirs(CACHE_DIR, exist_ok=True)
