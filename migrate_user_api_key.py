"""
Database Migration Script: Add GPT API Key field to Users table
Created: November 5, 2025
Purpose: Add encrypted GPT API key storage for users
"""

import sqlite3
import sys
import os
from pathlib import Path

def migrate_database():
    """Add gpt_api_key_encrypted column to users table"""
    
    # Database path
    db_path = "kitkool_bot.db"
    
    if not os.path.exists(db_path):
        print(f"❌ Database file {db_path} not found!")
        print("Please ensure you're running this script from the correct directory.")
        return False
    
    try:
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if column already exists
        cursor.execute("PRAGMA table_info(users)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'gpt_api_key_encrypted' in columns:
            print("✅ Column 'gpt_api_key_encrypted' already exists in users table.")
            return True
        
        # Add new column
        print("🔄 Adding 'gpt_api_key_encrypted' column to users table...")
        cursor.execute("""
            ALTER TABLE users 
            ADD COLUMN gpt_api_key_encrypted TEXT NULL
        """)
        
        # Commit changes
        conn.commit()
        print("✅ Successfully added 'gpt_api_key_encrypted' column to users table.")
        
        # Verify the change
        cursor.execute("PRAGMA table_info(users)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'gpt_api_key_encrypted' in columns:
            print("✅ Migration verified successfully.")
            return True
        else:
            print("❌ Migration verification failed.")
            return False
            
    except sqlite3.Error as e:
        print(f"❌ Database error during migration: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error during migration: {e}")
        return False
    finally:
        if 'conn' in locals():
            conn.close()

def rollback_migration():
    """Rollback the migration (remove the column)"""
    
    db_path = "kitkool_bot.db"
    
    if not os.path.exists(db_path):
        print(f"❌ Database file {db_path} not found!")
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if column exists
        cursor.execute("PRAGMA table_info(users)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'gpt_api_key_encrypted' not in columns:
            print("✅ Column 'gpt_api_key_encrypted' does not exist. Nothing to rollback.")
            return True
        
        print("🔄 Rolling back migration...")
        print("⚠️  Note: SQLite does not support DROP COLUMN directly.")
        print("⚠️  To fully rollback, you would need to recreate the table without this column.")
        print("⚠️  For now, we'll just clear the data in this column.")
        
        # Clear data in the column (since SQLite doesn't support DROP COLUMN easily)
        cursor.execute("UPDATE users SET gpt_api_key_encrypted = NULL")
        conn.commit()
        
        print("✅ Rollback completed (data cleared from gpt_api_key_encrypted column).")
        return True
        
    except sqlite3.Error as e:
        print(f"❌ Database error during rollback: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error during rollback: {e}")
        return False
    finally:
        if 'conn' in locals():
            conn.close()

def main():
    """Main migration function"""
    print("🚀 User GPT API Key Migration Script")
    print("=" * 50)
    
    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        print("🔄 Running rollback migration...")
        success = rollback_migration()
    else:
        print("🔄 Running forward migration...")
        success = migrate_database()
    
    if success:
        print("\n✅ Migration completed successfully!")
    else:
        print("\n❌ Migration failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()