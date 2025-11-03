import os
from datetime import datetime
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from database.db import SessionLocal
from model.admin_models import AdminUser, AdminSession
import config

class AdminAuthService:
    def __init__(self):
        self.default_admin_username = os.getenv("DEFAULT_ADMIN_USERNAME", config.DEFAULT_ADMIN_USERNAME if hasattr(config, 'DEFAULT_ADMIN_USERNAME') else "admin")
        self.default_admin_password = os.getenv("DEFAULT_ADMIN_PASSWORD", config.DEFAULT_ADMIN_PASSWORD if hasattr(config, 'DEFAULT_ADMIN_PASSWORD') else "admin123")
        self.default_admin_email = os.getenv("ADMIN_EMAIL", "admin@example.com")
        self.session_expire_hours = config.ADMIN_SESSION_EXPIRE_HOURS
    
    def initialize_default_admin(self) -> bool:
        """Create default admin user if none exists"""
        db: Session = SessionLocal()
        try:
            # Check if any admin exists
            existing_admin = db.query(AdminUser).first()
            if existing_admin:
                return True
            
            # Create default admin
            default_admin = AdminUser.create_admin(
                username=self.default_admin_username,
                email=self.default_admin_email,
                password=self.default_admin_password,
                full_name="System Administrator",
                is_super_admin=True
            )
            
            db.add(default_admin)
            db.commit()
            print(f"✅ Default admin created: {self.default_admin_username}")
            return True
            
        except Exception as e:
            db.rollback()
            print(f"❌ Failed to create default admin: {e}")
            return False
        finally:
            db.close()
    
    def authenticate_admin(self, username: str, password: str) -> Tuple[bool, Optional[str], Optional[dict]]:
        """Authenticate admin and create session"""
        db: Session = SessionLocal()
        try:
            # Find admin user
            admin = db.query(AdminUser).filter(
                AdminUser.username == username,
                AdminUser.is_active == True
            ).first()
            
            if not admin or not admin.verify_password(password):
                return False, None, None
            
            # Update last login
            admin.last_login = datetime.now()
            
            # Create session
            session = AdminSession.create_session(admin.id)
            db.add(session)
            db.commit()
            
            admin_info = {
                "id": admin.id,
                "username": admin.username,
                "email": admin.email,
                "full_name": admin.full_name,
                "is_super_admin": admin.is_super_admin
            }
            
            return True, session.session_token, admin_info
            
        except Exception as e:
            db.rollback()
            print(f"❌ Authentication error: {e}")
            return False, None, None
        finally:
            db.close()
    
    def validate_session(self, session_token: str) -> Tuple[bool, Optional[dict]]:
        """Validate admin session token"""
        db: Session = SessionLocal()
        try:
            # Find active session
            session = db.query(AdminSession).filter(
                AdminSession.session_token == session_token,
                AdminSession.is_active == True
            ).first()
            
            if not session or session.is_expired():
                return False, None
            
            # Get admin info
            admin = db.query(AdminUser).filter(
                AdminUser.id == session.admin_id,
                AdminUser.is_active == True
            ).first()
            
            if not admin:
                return False, None
            
            # Refresh session
            session.refresh_session()
            db.commit()
            
            admin_info = {
                "id": admin.id,
                "username": admin.username,
                "email": admin.email,
                "full_name": admin.full_name,
                "is_super_admin": admin.is_super_admin
            }
            
            return True, admin_info
            
        except Exception as e:
            print(f"❌ Session validation error: {e}")
            return False, None
        finally:
            db.close()
    
    def logout_admin(self, session_token: str) -> bool:
        """Logout admin by deactivating session"""
        db: Session = SessionLocal()
        try:
            session = db.query(AdminSession).filter(
                AdminSession.session_token == session_token
            ).first()
            
            if session:
                session.is_active = False
                db.commit()
                return True
            return False
            
        except Exception as e:
            db.rollback()
            print(f"❌ Logout error: {e}")
            return False
        finally:
            db.close()
    
    def create_admin_user(self, username: str, email: str, password: str, full_name: str = None, is_super_admin: bool = False) -> bool:
        """Create new admin user"""
        db: Session = SessionLocal()
        try:
            # Check if username/email exists
            existing = db.query(AdminUser).filter(
                (AdminUser.username == username) | (AdminUser.email == email)
            ).first()
            
            if existing:
                return False
            
            new_admin = AdminUser.create_admin(
                username=username,
                email=email,
                password=password,
                full_name=full_name,
                is_super_admin=is_super_admin
            )
            
            db.add(new_admin)
            db.commit()
            return True
            
        except Exception as e:
            db.rollback()
            print(f"❌ Failed to create admin user: {e}")
            return False
        finally:
            db.close()

# Global instance
admin_auth_service = AdminAuthService()