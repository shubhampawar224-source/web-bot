#!/usr/bin/env python3
"""
Quick Migration Runner
======================

Simple wrapper to run migrations with common options.

Usage Examples:
    python migrate.py                 # Run migrations with backup
    python migrate.py --preview       # Preview changes only
    python migrate.py --force         # Run without backup
    python migrate.py --help          # Show help
"""

import sys
import os
import subprocess

def main():
    """Run migration with simplified options"""
    
    # Default arguments for migrate_all.py
    args = []
    
    # Parse simple arguments
    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            if arg == '--preview':
                args.append('--dry-run')
            elif arg == '--force':
                args.append('--no-backup')
            elif arg == '--help':
                print(__doc__)
                print("\nAvailable options:")
                print("  --preview    Preview changes without applying")
                print("  --force      Run without creating backup")
                print("  --help       Show this help message")
                print("\nFor advanced options, use migrate_all.py directly")
                return
            else:
                args.append(arg)
    
    # Construct command
    cmd = [sys.executable, 'migrate_all.py'] + args
    
    print("🚀 Running migrations...")
    print(f"Command: {' '.join(cmd)}")
    print("-" * 40)
    
    # Run the migration
    try:
        result = subprocess.run(cmd, cwd=os.path.dirname(os.path.abspath(__file__)))
        sys.exit(result.returncode)
    except KeyboardInterrupt:
        print("\n⚠️ Migration cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error running migration: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()