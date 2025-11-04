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
        from model.user_models import User, UserSession
        
        # Create all tables
        Base.metadata.create_all(bind=engine)
        print("✅ Database tables created successfully!")
        
        # Run migration to add missing columns to existing tables
        try:
            migrate_existing_tables()
        except Exception as e:
            print(f"⚠️ Migration warning: {e}")
        
    except Exception as e:
        print(f"❌ Error creating database tables: {e}")
        raise

def migrate_existing_tables():
    """Add missing columns to existing tables"""
    from sqlalchemy import text
    
    with engine.connect() as connection:
        # Check if url_injection_requests table exists
        result = connection.execute(text("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='url_injection_requests';
        """))
        
        if result.fetchone():
            # Check existing columns
            result = connection.execute(text("PRAGMA table_info(url_injection_requests)"))
            columns = [row[1] for row in result.fetchall()]
            
            # Add missing columns
            columns_to_add = [
                ("user_id", "INTEGER"),
                ("description", "TEXT"),
                ("status", "VARCHAR(20) DEFAULT 'pending'")
            ]
            
            for column_name, column_type in columns_to_add:
                if column_name not in columns:
                    try:
                        connection.execute(text(f"""
                            ALTER TABLE url_injection_requests 
                            ADD COLUMN {column_name} {column_type}
                        """))
                        print(f"✅ Added missing column: {column_name}")
                    except Exception as e:
                        # Column might already exist, ignore the error
                        pass
            
            connection.commit()

def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()