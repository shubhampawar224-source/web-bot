from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv(override=True)  

# Use DATABASE_URL for the admin database (main app database)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./kitkool_bot.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def init_db():
    """Initialize database with all tables"""
    try:
        # Import all models to ensure they're registered with Base
        from model.models import Firm, Website, Contact
        from model.url_injection_models import URLInjectionRequest
        from model.admin_models import AdminUser, AdminSession
        
        # Create all tables
        Base.metadata.create_all(bind=engine)
        print("✅ Database tables created successfully!")
        
    except Exception as e:
        print(f"❌ Error creating database tables: {e}")
        raise

def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()