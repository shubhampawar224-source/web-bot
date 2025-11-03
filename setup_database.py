#!/usr/bin/env python3
"""
Complete database initialization script
Creates all tables and sets up default admin user
"""

import sys
import os
import sqlite3

# Add the current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database.db import init_db, engine, SessionLocal
from utils.admin_auth_service import AdminAuthService
import config

def reset_database():
    """Reset database by recreating all tables"""
    try:
        # For SQLite, we can just delete the file and recreate
        db_path = config.DATABASE_URL.replace("sqlite:///", "").replace("./", "")
        if os.path.exists(db_path):
            print(f"Removing existing database: {db_path}")
            os.remove(db_path)
        
        print("Creating fresh database...")
        init_db()
        
        return True
        
    except Exception as e:
        print(f"❌ Error resetting database: {e}")
        return False

def setup_admin():
    """Setup default admin user"""
    try:
        auth_service = AdminAuthService()
        success = auth_service.initialize_default_admin()
        
        if success:
            print("✅ Default admin user created successfully!")
            print(f"Username: {auth_service.default_admin_username}")
            print(f"Password: {auth_service.default_admin_password}")
            print(f"Email: {auth_service.default_admin_email}")
        else:
            print("❌ Failed to create default admin user")
            
        return success
        
    except Exception as e:
        print(f"❌ Error setting up admin: {e}")
        return False

def main():
    """Main initialization function"""
    print("🔄 Initializing KitKool Bot Database...")
    print("=" * 50)
    
    # Step 1: Reset and create database
    if not reset_database():
        print("❌ Database initialization failed!")
        return False
    
    # Step 2: Setup default admin
    if not setup_admin():
        print("❌ Admin setup failed!")
        return False
    
    print("=" * 50)
    print("✅ Database initialization completed successfully!")
    print("\nNext steps:")
    print("1. Configure Google OAuth in .env file (optional)")
    print("2. Start the application: python mains.py")
    print("3. Access admin panel: http://localhost:8000/admin")
    
    return True

if __name__ == "__main__":
    main()