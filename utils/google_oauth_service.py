import os
import secrets
from typing import Optional, Dict, Tuple
from authlib.integrations.starlette_client import OAuth
from authlib.jose import jwt
from sqlalchemy.orm import Session
from database.db import SessionLocal
from model.admin_models import AdminUser, AdminSession
import config
import httpx
import json

class GoogleOAuthService:
    def __init__(self):
        self.client_id = config.GOOGLE_CLIENT_ID
        self.client_secret = config.GOOGLE_CLIENT_SECRET
        self.redirect_uri = config.GOOGLE_REDIRECT_URI or "http://127.0.0.1:8000/admin/oauth/callback"
        self.scope = "openid email profile"
        
        # Allowed domains for admin access (optional)
        self.allowed_domains = os.getenv("ADMIN_ALLOWED_DOMAINS", "").split(",") if os.getenv("ADMIN_ALLOWED_DOMAINS") else []
        
        # OAuth configuration
        self.oauth = OAuth()
        self.oauth.register(
            name='google',
            client_id=self.client_id,
            client_secret=self.client_secret,
            server_metadata_url='https://accounts.google.com/.well-known/openid_configuration',
            client_kwargs={
                'scope': self.scope
            }
        )
    
    def get_authorization_url(self, state: str = None) -> str:
        """Generate Google OAuth authorization URL"""
        if not state:
            state = secrets.token_urlsafe(32)
        
        return (
            f"https://accounts.google.com/o/oauth2/auth?"
            f"client_id={self.client_id}&"
            f"redirect_uri={self.redirect_uri}&"
            f"scope={self.scope.replace(' ', '%20')}&"
            f"response_type=code&"
            f"access_type=offline&"
            f"state={state}"
        )
    
    async def exchange_code_for_token(self, code: str) -> Optional[Dict]:
        """Exchange authorization code for access token"""
        try:
            token_url = "https://oauth2.googleapis.com/token"
            
            data = {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": self.redirect_uri,
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(token_url, data=data)
                
            if response.status_code == 200:
                return response.json()
            else:
                print(f"Token exchange failed: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            print(f"Error exchanging code for token: {e}")
            return None
    
    async def get_user_info(self, access_token: str) -> Optional[Dict]:
        """Get user information from Google using access token"""
        try:
            user_info_url = "https://www.googleapis.com/oauth2/v2/userinfo"
            
            headers = {"Authorization": f"Bearer {access_token}"}
            
            async with httpx.AsyncClient() as client:
                response = await client.get(user_info_url, headers=headers)
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"Failed to get user info: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            print(f"Error getting user info: {e}")
            return None
    
    def is_email_allowed(self, email: str) -> bool:
        """Check if email domain is allowed for admin access"""
        if not self.allowed_domains:
            return True  # If no restrictions, allow all
        
        domain = email.split("@")[1] if "@" in email else ""
        return domain in self.allowed_domains
    
    def create_or_update_admin_user(self, user_info: Dict) -> Tuple[bool, Optional[AdminUser], str]:
        """Create or update admin user from Google OAuth info"""
        db: Session = SessionLocal()
        try:
            email = user_info.get("email")
            google_id = user_info.get("id")
            
            if not email or not google_id:
                return False, None, "Invalid user information from Google"
            
            # Check if email is allowed
            if not self.is_email_allowed(email):
                return False, None, f"Email domain not allowed for admin access"
            
            # Check if user exists by email or Google ID
            existing_user = db.query(AdminUser).filter(
                (AdminUser.email == email) | (AdminUser.google_id == google_id)
            ).first()
            
            if existing_user:
                # Update existing user
                existing_user.google_id = google_id
                existing_user.full_name = user_info.get("name")
                existing_user.profile_picture = user_info.get("picture")
                existing_user.auth_provider = "google"
                existing_user.last_login = datetime.now()
                
                if not existing_user.is_active:
                    return False, None, "User account is deactivated"
                
                db.commit()
                db.refresh(existing_user)
                return True, existing_user, "User updated successfully"
            
            else:
                # Create new user
                # Check if this is the first Google user (make them super admin)
                existing_google_users = db.query(AdminUser).filter(
                    AdminUser.auth_provider == "google"
                ).count()
                
                is_super_admin = existing_google_users == 0  # First Google user becomes super admin
                
                new_user = AdminUser.create_from_google(user_info, is_super_admin=is_super_admin)
                new_user.last_login = datetime.now()
                
                db.add(new_user)
                db.commit()
                db.refresh(new_user)
                
                return True, new_user, "New admin user created successfully"
                
        except Exception as e:
            db.rollback()
            print(f"Error creating/updating admin user: {e}")
            return False, None, f"Database error: {str(e)}"
        finally:
            db.close()
    
    def create_admin_session(self, admin_user: AdminUser) -> Optional[str]:
        """Create admin session for OAuth user"""
        db: Session = SessionLocal()
        try:
            session = AdminSession.create_session(admin_user.id)
            db.add(session)
            db.commit()
            
            return session.session_token
            
        except Exception as e:
            db.rollback()
            print(f"Error creating admin session: {e}")
            return None
        finally:
            db.close()
    
    def get_admin_info_dict(self, admin_user: AdminUser) -> Dict:
        """Convert admin user to dictionary for frontend"""
        return {
            "id": admin_user.id,
            "username": admin_user.username,
            "email": admin_user.email,
            "full_name": admin_user.full_name,
            "is_super_admin": admin_user.is_super_admin,
            "profile_picture": admin_user.profile_picture,
            "auth_provider": admin_user.auth_provider
        }

# Add missing import
from datetime import datetime

# Global instance
google_oauth_service = GoogleOAuthService()