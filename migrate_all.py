#!/usr/bin/env python3
"""
Universal Migration System
==========================

This script automatically detects and applies all necessary database migrations 
for any changes in the model/ directory.

Features:
- Auto-discovers all model files in model/ directory
- Creates tables for new models
- Adds missing columns to existing tables
- Handles foreign key relationships
- Backup database before migrations
- Rollback capability on errors
- Detailed logging and verification

Usage:
    python migrate_all.py              # Run all migrations
    python migrate_all.py --dry-run    # Preview changes without applying
    python migrate_all.py --backup     # Create backup before migration
    python migrate_all.py --verify     # Verify migrations after completion
"""

import os
import sys
import argparse
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
import importlib.util
import inspect
import hashlib
import json
from typing import List, Dict, Any, Tuple
from sqlalchemy import create_engine, inspect as sqlalchemy_inspect, text, MetaData, Table, Column, Integer, String, DateTime, Text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./kitkool_bot.db")

class MigrationManager:
    """Manages all database migrations automatically"""
    
    def __init__(self, database_url: str = DATABASE_URL):
        self.database_url = database_url
        self.engine = create_engine(database_url, connect_args={"check_same_thread": False})
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self.inspector = sqlalchemy_inspect(self.engine)
        
        # Import database base
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        from database.db import Base
        self.Base = Base
        
        # Migration tracking
        self.migrations_applied = []
        self.errors = []
        
        # Initialize migration history table
        self._ensure_migration_history_table()
        
        print(f"🔧 Migration Manager initialized for: {database_url}")
    
    def _ensure_migration_history_table(self):
        """Ensure migration history table exists"""
        create_sql = """
        CREATE TABLE IF NOT EXISTS migration_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            migration_id VARCHAR(255) NOT NULL,
            description TEXT,
            applied_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            model_file VARCHAR(255),
            model_hash VARCHAR(64),
            success BOOLEAN DEFAULT FALSE,
            error_message TEXT
        )
        """
        
        with self.engine.connect() as connection:
            connection.execute(text(create_sql))
            connection.commit()
    
    def _calculate_model_hash(self, model_file: Path) -> str:
        """Calculate hash of model file to detect changes"""
        with open(model_file, 'rb') as f:
            return hashlib.sha256(f.read()).hexdigest()
    
    def _log_migration(self, migration_id: str, description: str, model_file: str = None, 
                      model_hash: str = None, success: bool = True, error_message: str = None):
        """Log migration to history table"""
        insert_sql = """
        INSERT INTO migration_history 
        (migration_id, description, model_file, model_hash, success, error_message)
        VALUES (?, ?, ?, ?, ?, ?)
        """
        
        with self.engine.connect() as connection:
            connection.execute(text(insert_sql), [
                migration_id, description, model_file, model_hash, success, error_message
            ])
            connection.commit()
    
    def get_migration_history(self) -> List[Dict]:
        """Get migration history"""
        select_sql = "SELECT * FROM migration_history ORDER BY applied_at DESC LIMIT 50"
        
        with self.engine.connect() as connection:
            result = connection.execute(text(select_sql))
            columns = result.keys()
            return [dict(zip(columns, row)) for row in result.fetchall()]
    
    def discover_models(self) -> Dict[str, List[Any]]:
        """Discover all SQLAlchemy model classes in model/ directory"""
        models = {}
        model_dir = Path("model")
        
        if not model_dir.exists():
            raise Exception("model/ directory not found!")
        
        print("🔍 Discovering model files...")
        
        for model_file in model_dir.glob("*.py"):
            if model_file.name.startswith("__"):
                continue
                
            print(f"   📄 Scanning {model_file.name}")
            
            try:
                # Calculate file hash for change tracking
                file_hash = self._calculate_model_hash(model_file)
                
                # Import the module
                spec = importlib.util.spec_from_file_location(
                    f"model.{model_file.stem}", 
                    model_file
                )
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                # Find SQLAlchemy model classes
                model_classes = []
                for name, obj in inspect.getmembers(module):
                    if (inspect.isclass(obj) and 
                        hasattr(obj, '__tablename__') and 
                        hasattr(obj, '__table__')):
                        model_classes.append(obj)
                        print(f"      ✅ Found model: {name} -> {obj.__tablename__}")
                
                if model_classes:
                    models[model_file.name] = {
                        'classes': model_classes,
                        'hash': file_hash,
                        'path': str(model_file)
                    }
                    
            except Exception as e:
                print(f"      ❌ Error importing {model_file.name}: {e}")
                self.errors.append(f"Import error in {model_file.name}: {e}")
        
        total_models = sum(len(data['classes']) for data in models.values())
        print(f"📊 Discovered {total_models} models in {len(models)} files")
        return models
    
    def get_existing_tables(self) -> List[str]:
        """Get list of existing database tables"""
        existing_tables = self.inspector.get_table_names()
        print(f"📋 Existing tables: {existing_tables}")
        return existing_tables
    
    def get_table_columns(self, table_name: str) -> List[str]:
        """Get list of columns for a specific table"""
        try:
            columns = [col['name'] for col in self.inspector.get_columns(table_name)]
            return columns
        except Exception:
            return []
    
    def backup_database(self) -> str:
        """Create a backup of the current database"""
        if not self.database_url.startswith('sqlite'):
            print("⚠️ Backup only supported for SQLite databases")
            return None
        
        # Extract database file path from URL
        db_path = self.database_url.replace('sqlite:///', '')
        if db_path.startswith('./'):
            db_path = db_path[2:]
        
        if not os.path.exists(db_path):
            print(f"⚠️ Database file {db_path} doesn't exist yet")
            return None
        
        # Create backup with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{db_path}.backup_{timestamp}"
        
        try:
            shutil.copy2(db_path, backup_path)
            print(f"💾 Database backed up to: {backup_path}")
            return backup_path
        except Exception as e:
            print(f"❌ Backup failed: {e}")
            return None
    
    def create_new_tables(self, models: Dict[str, Dict], dry_run: bool = False) -> List[str]:
        """Create tables for new models"""
        existing_tables = self.get_existing_tables()
        new_tables = []
        
        print("🔨 Checking for new tables to create...")
        
        for file_name, model_data in models.items():
            model_classes = model_data['classes']
            file_hash = model_data['hash']
            
            for model_class in model_classes:
                table_name = model_class.__tablename__
                
                if table_name not in existing_tables:
                    new_tables.append(table_name)
                    print(f"   📋 New table needed: {table_name} (from {file_name})")
                    
                    migration_id = f"create_table_{table_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    
                    if not dry_run:
                        try:
                            # Create the specific table
                            model_class.__table__.create(self.engine, checkfirst=True)
                            print(f"      ✅ Created table: {table_name}")
                            self.migrations_applied.append(f"Created table: {table_name}")
                            
                            # Log migration
                            self._log_migration(
                                migration_id,
                                f"Created table {table_name}",
                                file_name,
                                file_hash,
                                True
                            )
                            
                        except Exception as e:
                            error_msg = f"Failed to create table {table_name}: {e}"
                            print(f"      ❌ {error_msg}")
                            self.errors.append(error_msg)
                            
                            # Log error
                            self._log_migration(
                                migration_id,
                                f"Failed to create table {table_name}",
                                file_name,
                                file_hash,
                                False,
                                str(e)
                            )
        
        if not new_tables:
            print("   ✅ No new tables needed")
        
        return new_tables
    
    def add_missing_columns(self, models: Dict[str, Dict], dry_run: bool = False) -> List[str]:
        """Add missing columns to existing tables"""
        print("🔧 Checking for missing columns...")
        missing_columns = []
        
        for file_name, model_data in models.items():
            model_classes = model_data['classes']
            file_hash = model_data['hash']
            
            for model_class in model_classes:
                table_name = model_class.__tablename__
                
                # Skip if table doesn't exist
                if table_name not in self.inspector.get_table_names():
                    continue
                
                # Get existing columns
                existing_columns = self.get_table_columns(table_name)
                
                # Get required columns from model
                model_columns = [col.name for col in model_class.__table__.columns]
                
                # Find missing columns
                missing = [col for col in model_columns if col not in existing_columns]
                
                if missing:
                    print(f"   📋 Table {table_name} missing columns: {missing}")
                    
                    for col_name in missing:
                        column_info = f"{table_name}.{col_name}"
                        missing_columns.append(column_info)
                        
                        migration_id = f"add_column_{table_name}_{col_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                        
                        if not dry_run:
                            try:
                                # Get column definition from model
                                column_obj = None
                                for col in model_class.__table__.columns:
                                    if col.name == col_name:
                                        column_obj = col
                                        break
                                
                                if column_obj is not None:
                                    self._add_column_to_table(table_name, column_obj)
                                    print(f"      ✅ Added column: {column_info}")
                                    self.migrations_applied.append(f"Added column: {column_info}")
                                    
                                    # Log migration
                                    self._log_migration(
                                        migration_id,
                                        f"Added column {column_info}",
                                        file_name,
                                        file_hash,
                                        True
                                    )
                                    
                                else:
                                    error_msg = f"Column definition not found for {column_info}"
                                    print(f"      ❌ {error_msg}")
                                    self.errors.append(error_msg)
                                    
                                    # Log error
                                    self._log_migration(
                                        migration_id,
                                        f"Failed to add column {column_info}",
                                        file_name,
                                        file_hash,
                                        False,
                                        error_msg
                                    )
                                    
                            except Exception as e:
                                error_msg = f"Failed to add column {column_info}: {e}"
                                print(f"      ❌ {error_msg}")
                                self.errors.append(error_msg)
                                
                                # Log error
                                self._log_migration(
                                    migration_id,
                                    f"Failed to add column {column_info}",
                                    file_name,
                                    file_hash,
                                    False,
                                    str(e)
                                )
        
        if not missing_columns:
            print("   ✅ No missing columns found")
        
        return missing_columns
    
    def _add_column_to_table(self, table_name: str, column_obj):
        """Add a single column to an existing table"""
        # Generate SQL for adding column
        column_type = str(column_obj.type.compile(dialect=self.engine.dialect))
        
        # Handle nullable and default values
        nullable_clause = "" if column_obj.nullable else " NOT NULL"
        default_clause = ""
        
        if column_obj.default is not None:
            if hasattr(column_obj.default, 'arg'):
                default_value = column_obj.default.arg
                if isinstance(default_value, str):
                    default_clause = f" DEFAULT '{default_value}'"
                else:
                    default_clause = f" DEFAULT {default_value}"
        
        sql = f"ALTER TABLE {table_name} ADD COLUMN {column_obj.name} {column_type}{nullable_clause}{default_clause}"
        
        with self.engine.connect() as connection:
            connection.execute(text(sql))
            connection.commit()
    
    def verify_migrations(self, models: Dict[str, Dict]) -> bool:
        """Verify that all migrations were applied correctly"""
        print("🔍 Verifying migrations...")
        verification_passed = True
        
        for file_name, model_data in models.items():
            model_classes = model_data['classes']
            
            for model_class in model_classes:
                table_name = model_class.__tablename__
                
                # Check if table exists
                if table_name not in self.inspector.get_table_names():
                    print(f"   ❌ Table {table_name} not found")
                    verification_passed = False
                    continue
                
                # Check if all columns exist
                existing_columns = self.get_table_columns(table_name)
                model_columns = [col.name for col in model_class.__table__.columns]
                
                missing_columns = [col for col in model_columns if col not in existing_columns]
                
                if missing_columns:
                    print(f"   ❌ Table {table_name} still missing columns: {missing_columns}")
                    verification_passed = False
                else:
                    print(f"   ✅ Table {table_name} verified")
        
        return verification_passed
    
    def run_migrations(self, dry_run: bool = False, create_backup: bool = True, verify: bool = True) -> bool:
        """Run all necessary migrations"""
        print("🚀 Starting migration process...")
        print(f"   Dry run: {dry_run}")
        print(f"   Backup: {create_backup}")
        print(f"   Verify: {verify}")
        print("-" * 50)
        
        # Create backup if requested
        backup_path = None
        if create_backup and not dry_run:
            backup_path = self.backup_database()
        
        try:
            # Discover all models
            models = self.discover_models()
            
            if not models:
                print("❌ No models found!")
                return False
            
            # Create new tables
            new_tables = self.create_new_tables(models, dry_run)
            
            # Add missing columns
            missing_columns = self.add_missing_columns(models, dry_run)
            
            # Verify migrations if requested
            if verify and not dry_run:
                verification_passed = self.verify_migrations(models)
                if not verification_passed:
                    print("❌ Migration verification failed!")
                    return False
            
            # Summary
            print("-" * 50)
            print("📊 Migration Summary:")
            print(f"   New tables created: {len(new_tables)}")
            print(f"   Missing columns added: {len(missing_columns)}")
            print(f"   Total migrations applied: {len(self.migrations_applied)}")
            print(f"   Errors encountered: {len(self.errors)}")
            
            if self.migrations_applied:
                print("✅ Applied migrations:")
                for migration in self.migrations_applied:
                    print(f"   - {migration}")
            
            if self.errors:
                print("❌ Errors:")
                for error in self.errors:
                    print(f"   - {error}")
                return False
            
            if dry_run:
                print("🔍 Dry run completed - no changes applied")
            else:
                print("✅ All migrations completed successfully!")
            
            return True
            
        except Exception as e:
            print(f"❌ Migration failed: {e}")
            self.errors.append(str(e))
            
            # Restore backup if available
            if backup_path and os.path.exists(backup_path):
                print(f"🔄 Attempting to restore backup from {backup_path}")
                try:
                    db_path = self.database_url.replace('sqlite:///', '')
                    if db_path.startswith('./'):
                        db_path = db_path[2:]
                    shutil.copy2(backup_path, db_path)
                    print("✅ Database restored from backup")
                except Exception as restore_error:
                    print(f"❌ Failed to restore backup: {restore_error}")
            
            return False

def main():
    parser = argparse.ArgumentParser(description="Universal Migration System")
    parser.add_argument('--dry-run', action='store_true', 
                       help='Preview changes without applying them')
    parser.add_argument('--backup', action='store_true', default=True,
                       help='Create backup before migration (default: True)')
    parser.add_argument('--no-backup', action='store_true', 
                       help='Skip backup creation')
    parser.add_argument('--verify', action='store_true', default=True,
                       help='Verify migrations after completion (default: True)')
    parser.add_argument('--no-verify', action='store_true', 
                       help='Skip verification')
    parser.add_argument('--history', action='store_true',
                       help='Show migration history and exit')
    parser.add_argument('--status', action='store_true',
                       help='Show current database status and exit')
    
    args = parser.parse_args()
    
    print("🔄 Universal Migration System")
    print("=" * 30)
    
    try:
        migration_manager = MigrationManager()
        
        # Handle history command
        if args.history:
            print("📜 Migration History:")
            print("-" * 50)
            history = migration_manager.get_migration_history()
            if history:
                for entry in history:
                    status = "✅" if entry['success'] else "❌"
                    timestamp = entry['applied_at']
                    print(f"{status} {timestamp} - {entry['description']}")
                    if entry['model_file']:
                        print(f"    File: {entry['model_file']}")
                    if not entry['success'] and entry['error_message']:
                        print(f"    Error: {entry['error_message']}")
                    print()
            else:
                print("No migration history found.")
            return
        
        # Handle status command
        if args.status:
            print("📊 Database Status:")
            print("-" * 50)
            
            # Show existing tables
            tables = migration_manager.get_existing_tables()
            print(f"Existing tables: {len(tables)}")
            for table in sorted(tables):
                columns = migration_manager.get_table_columns(table)
                print(f"  📋 {table} ({len(columns)} columns)")
            
            # Show models that would be discovered
            models = migration_manager.discover_models()
            print(f"\nDiscovered models: {sum(len(data['classes']) for data in models.values())}")
            for file_name, model_data in models.items():
                print(f"  📄 {file_name} ({len(model_data['classes'])} models)")
                for model_class in model_data['classes']:
                    table_name = model_class.__tablename__
                    exists = "✅" if table_name in tables else "❌"
                    print(f"    {exists} {table_name}")
            
            return
        
        # Handle backup flags
        create_backup = args.backup and not args.no_backup
        
        # Handle verify flags
        verify = args.verify and not args.no_verify
        
        success = migration_manager.run_migrations(
            dry_run=args.dry_run,
            create_backup=create_backup,
            verify=verify
        )
        
        if success:
            print("\n✅ Migration process completed successfully!")
            sys.exit(0)
        else:
            print("\n❌ Migration process failed!")
            sys.exit(1)
            
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()