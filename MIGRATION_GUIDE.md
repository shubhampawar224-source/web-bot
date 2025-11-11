# Universal Migration System Documentation
========================================

## Overview

The Universal Migration System automatically detects changes in your model files and applies all necessary database migrations with a single command. It's designed to handle SQLAlchemy models and works with SQLite databases by default.

## Features

✅ **Auto-Discovery**: Automatically finds all SQLAlchemy models in the `model/` directory  
✅ **Smart Detection**: Creates new tables and adds missing columns  
✅ **Backup System**: Creates automatic backups before migrations  
✅ **Migration History**: Tracks all applied migrations with timestamps  
✅ **Dry Run Mode**: Preview changes without applying them  
✅ **Verification**: Automatically verifies migrations after completion  
✅ **Error Handling**: Comprehensive error logging and rollback capability  
✅ **Multiple Interfaces**: Command line, Python script, and Windows batch file  

## Quick Start

### Basic Usage

```bash
# Run all migrations (recommended)
python migrate.py

# Preview what would be changed without applying
python migrate.py --preview

# Run without backup (not recommended)
python migrate.py --force
```

### Windows Users

```cmd
# Run migrations
migrate.bat

# Preview changes only
migrate.bat preview

# Run without backup
migrate.bat force

# Show help
migrate.bat help
```

## Advanced Usage

### Using migrate_all.py directly

```bash
# Show current database status
python migrate_all.py --status

# Show migration history
python migrate_all.py --history

# Run dry run (preview only)
python migrate_all.py --dry-run

# Run without backup
python migrate_all.py --no-backup

# Run without verification
python migrate_all.py --no-verify

# Combine options
python migrate_all.py --dry-run --no-backup
```

## How It Works

### 1. Model Discovery
The system scans the `model/` directory for Python files and automatically discovers SQLAlchemy model classes by looking for:
- Classes with `__tablename__` attribute
- Classes with `__table__` attribute
- Classes that inherit from SQLAlchemy Base

### 2. Change Detection
For each model, the system:
- Calculates file hash to detect changes
- Compares model schema with existing database tables
- Identifies new tables that need to be created
- Finds missing columns in existing tables

### 3. Migration Application
The system applies changes in the following order:
1. **Backup**: Creates timestamped backup of database
2. **Create Tables**: Creates any new tables from new models
3. **Add Columns**: Adds missing columns to existing tables
4. **Verification**: Verifies all changes were applied correctly
5. **Logging**: Records all operations in migration history

### 4. History Tracking
Every migration is logged with:
- Unique migration ID
- Description of what was changed
- Source model file and hash
- Timestamp
- Success/failure status
- Error messages (if any)

## File Structure

```
web-bot/
├── migrate_all.py          # Full-featured migration system
├── migrate.py              # Simple wrapper script
├── migrate.bat             # Windows batch file
├── migration.conf          # Configuration file
└── model/                  # Your model directory
    ├── admin_models.py
    ├── models.py
    ├── user_models.py
    └── ...
```

## Configuration

Edit `migration.conf` to customize behavior:

```ini
[database]
url = sqlite:///./kitkool_bot.db
backup_enabled = true
backup_retention_days = 30

[migration]
model_directory = model/
auto_verify = true

[safety]
require_confirmation = false
max_tables_per_run = 50
```

## Common Scenarios

### Adding a New Model
1. Create your new model class in any `.py` file in the `model/` directory
2. Run `python migrate.py`
3. The system will automatically create the table

Example:
```python
# model/new_models.py
from database.db import Base
from sqlalchemy import Column, Integer, String, DateTime

class NewModel(Base):
    __tablename__ = "new_table"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255))
    created_at = Column(DateTime)
```

### Adding New Columns
1. Add columns to your existing model class
2. Run `python migrate.py`
3. The system will automatically add the missing columns

Example:
```python
# model/existing_models.py
class ExistingModel(Base):
    __tablename__ = "existing_table"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255))
    # Add new columns here
    description = Column(Text, nullable=True)  # New column
    is_active = Column(Boolean, default=True)  # New column
```

### Creating a New Model File
1. Create a new `.py` file in the `model/` directory
2. Define your models using SQLAlchemy syntax
3. Run `python migrate.py`

## Best Practices

### 🛡️ Safety First
- Always run with `--preview` first to see what will change
- Backup is enabled by default - don't disable it unless you're sure
- Test migrations on development environment first

### 📁 Organization
- Keep related models in the same file
- Use descriptive filenames (e.g., `user_models.py`, `order_models.py`)
- Follow consistent naming conventions

### 🔍 Monitoring
- Check migration history regularly with `--history`
- Review database status with `--status`
- Monitor for errors in migration logs

## Troubleshooting

### Common Issues

**Issue**: "Table already defined" error
```
Solution: Check for duplicate model definitions across files
```

**Issue**: Migration fails to add column
```
Solution: 
1. Check if column has compatible default value
2. Ensure nullable columns or provide defaults for NOT NULL
3. Check column type compatibility
```

**Issue**: Model not discovered
```
Solution:
1. Ensure model inherits from Base
2. Verify __tablename__ is defined
3. Check for syntax errors in model file
```

### Debug Commands

```bash
# Check what models are discovered
python migrate_all.py --status

# See recent migration history
python migrate_all.py --history

# Run in dry-run mode to see potential issues
python migrate_all.py --dry-run
```

### Manual Recovery

If something goes wrong:

1. **Restore from backup**:
   ```bash
   # Find backup file (format: database.db.backup_YYYYMMDD_HHMMSS)
   ls *.backup_*
   
   # Restore (replace with actual backup filename)
   cp kitkool_bot.db.backup_20241111_143022 kitkool_bot.db
   ```

2. **Check migration history**:
   ```bash
   python migrate_all.py --history
   ```

3. **Verify current state**:
   ```bash
   python migrate_all.py --status
   ```

## Migration History

View your migration history:

```bash
python migrate_all.py --history
```

Example output:
```
📜 Migration History:
--------------------------------------------------
✅ 2024-11-11 14:30:22 - Created table new_orders
    File: order_models.py

✅ 2024-11-11 14:25:15 - Added column users.phone
    File: user_models.py

❌ 2024-11-11 14:20:10 - Failed to add column products.price
    File: product_models.py
    Error: NOT NULL constraint failed
```

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review migration history for errors
3. Run with `--dry-run` to preview changes
4. Create an issue in the project repository

## Version History

- **v1.0.0**: Initial release with auto-discovery and migration
- **v1.1.0**: Added migration history tracking
- **v1.2.0**: Added status and history commands
- **v1.3.0**: Added Windows batch file support