import os
import re
from datetime import datetime
from typing import Optional, Tuple, Dict
from sqlalchemy.orm import Session
from database.db import SessionLocal
from model.user_models import User, UserSession

class UserAuthService:
    def __init__(self):
        self.session_expire_hours = 168  # 7 days for regular users
        self.password_min_length = 8
    
    def validate_email(self, email: str) -> bool:
        """Validate email format"""
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(email_pattern, email) is not None
    
    def validate_password(self, password: str) -> Tuple[bool, str]:
        """Validate password strength"""
        if len(password) < self.password_min_length:
            return False, f"Password must be at least {self.password_min_length} characters long"
        
        # Check for at least one uppercase letter
        if not re.search(r'[A-Z]', password):
            return False, "Password must contain at least one uppercase letter"
        
        # Check for at least one lowercase letter
        if not re.search(r'[a-z]', password):
            return False, "Password must contain at least one lowercase letter"
        
        # Check for at least one digit
        if not re.search(r'\d', password):
            return False, "Password must contain at least one number"
        
        # Check for at least one special character
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            return False, "Password must contain at least one special character"
        
        return True, "Password is valid"
    
    def register_user(self, first_name: str, last_name: str, email: str, password: str, 
                     phone: str = None) -> Tuple[bool, str, Optional[Dict]]:
        """Register a new user"""
        db: Session = SessionLocal()
        try:
            # Validate input
            if not first_name or not first_name.strip():
                return False, "First name is required", None
            
            if not last_name or not last_name.strip():
                return False, "Last name is required", None
            
            if not self.validate_email(email):
                return False, "Invalid email format", None
            
            is_valid_password, password_message = self.validate_password(password)
            if not is_valid_password:
                return False, password_message, None
            
            # Check if email already exists
            existing_user = db.query(User).filter(User.email == email.lower()).first()
            if existing_user:
                return False, "Email address is already registered", None
            
            # Create new user
            new_user = User.create_user(
                first_name=first_name.strip(),
                last_name=last_name.strip(),
                email=email.lower(),
                password=password,
                phone=phone.strip() if phone else None
            )
            
            db.add(new_user)
            db.commit()
            db.refresh(new_user)
            
            user_info = {
                "id": new_user.id,
                "first_name": new_user.first_name,
                "last_name": new_user.last_name,
                "email": new_user.email,
                "full_name": new_user.full_name,
                "phone": new_user.phone,
                "created_at": new_user.created_at.isoformat()
            }
            
            return True, "User registered successfully", user_info
            
        except Exception as e:
            db.rollback()
            print(f"❌ Registration error: {e}")
            return False, "Registration failed. Please try again.", None
        finally:
            db.close()
    
    def authenticate_user(self, email: str, password: str, device_info: str = None, 
                         ip_address: str = None) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """Authenticate user and create session"""
        db: Session = SessionLocal()
        try:
            # Find user
            user = db.query(User).filter(
                User.email == email.lower(),
                User.is_active == True
            ).first()
            
            if not user or not user.verify_password(password):
                return False, None, None
            
            # Update last login
            user.last_login = datetime.now()
            
            # Create session
            session = UserSession.create_session(
                user.id, 
                self.session_expire_hours,
                device_info,
                ip_address
            )
            db.add(session)
            db.commit()
            
            user_info = {
                "id": user.id,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "email": user.email,
                "full_name": user.full_name,
                "phone": user.phone,
                "is_verified": user.is_verified
            }
            
            return True, session.session_token, user_info
            
        except Exception as e:
            db.rollback()
            print(f"❌ Authentication error: {e}")
            return False, None, None
        finally:
            db.close()
    
    def validate_session(self, session_token: str) -> Tuple[bool, Optional[Dict]]:
        """Validate user session token"""
        db: Session = SessionLocal()
        try:
            # Find active session
            session = db.query(UserSession).filter(
                UserSession.session_token == session_token,
                UserSession.is_active == True
            ).first()
            
            if not session or session.is_expired():
                return False, None
            
            # Get user info
            user = db.query(User).filter(
                User.id == session.user_id,
                User.is_active == True
            ).first()
            
            if not user:
                return False, None
            
            # Refresh session
            session.refresh_session()
            db.commit()
            
            user_info = {
                "id": user.id,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "email": user.email,
                "full_name": user.full_name,
                "phone": user.phone,
                "is_verified": user.is_verified
            }
            
            return True, user_info
            
        except Exception as e:
            print(f"❌ Session validation error: {e}")
            return False, None
        finally:
            db.close()
    
    def logout_user(self, session_token: str) -> bool:
        """Logout user by deactivating session"""
        db: Session = SessionLocal()
        try:
            session = db.query(UserSession).filter(
                UserSession.session_token == session_token
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
    
    def get_user_by_id(self, user_id: int) -> Optional[Dict]:
        """Get user information by ID"""
        db: Session = SessionLocal()
        try:
            user = db.query(User).filter(
                User.id == user_id,
                User.is_active == True
            ).first()
            
            if not user:
                return None
            
            return {
                "id": user.id,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "email": user.email,
                "full_name": user.full_name,
                "phone": user.phone,
                "is_verified": user.is_verified,
                "created_at": user.created_at.isoformat(),
                "last_login": user.last_login.isoformat() if user.last_login else None
            }
            
        except Exception as e:
            print(f"❌ Error getting user: {e}")
            return None
        finally:
            db.close()
    
    def update_user_profile(self, user_id: int, first_name: str = None, last_name: str = None, 
                           phone: str = None) -> Tuple[bool, str]:
        """Update user profile information"""
        db: Session = SessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return False, "User not found"
            
            if first_name and first_name.strip():
                user.first_name = first_name.strip()
            
            if last_name and last_name.strip():
                user.last_name = last_name.strip()
            
            if phone is not None:
                user.phone = phone.strip() if phone else None
            
            db.commit()
            return True, "Profile updated successfully"
            
        except Exception as e:
            db.rollback()
            print(f"❌ Profile update error: {e}")
            return False, "Failed to update profile"
        finally:
            db.close()

# Global instance
user_auth_service = UserAuthService()