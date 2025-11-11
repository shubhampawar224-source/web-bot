@echo off
REM Universal Migration Script for Windows
REM ======================================

echo 🚀 Starting Universal Migration System...

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python not found! Please install Python and add it to PATH.
    pause
    exit /b 1
)

REM Check if we're in the right directory
if not exist "migrate_all.py" (
    echo ❌ migrate_all.py not found! Please run this from the project root directory.
    pause
    exit /b 1
)

REM Check command line arguments
if "%1"=="preview" (
    echo 🔍 Running migration preview...
    python migrate_all.py --dry-run
) else if "%1"=="force" (
    echo ⚡ Running migration without backup...
    python migrate_all.py --no-backup
) else if "%1"=="help" (
    echo.
    echo Universal Migration System - Windows Batch Runner
    echo.
    echo Usage:
    echo   migrate.bat           - Run migrations with backup
    echo   migrate.bat preview   - Preview changes only
    echo   migrate.bat force     - Run without backup
    echo   migrate.bat help      - Show this help
    echo.
    echo For advanced options, use: python migrate_all.py [options]
    echo.
) else (
    echo 🔄 Running migrations with backup...
    python migrate_all.py
)

echo.
echo ✅ Migration script completed.
pause