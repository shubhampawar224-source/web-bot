from datetime import datetime, timedelta
from typing import Optional
import secrets
import hashlib
import base64
from cryptography.fernet import Fernet
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text
from database.db import Base

class AdminUser(Base):
    __tablename__ = "admin_users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=True)  # Allow null for OAuth users
    full_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    is_super_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)
    last_login = Column(DateTime, nullable=True)
    
    # OAuth fields
    google_id = Column(String(255), nullable=True, unique=True, index=True)
    profile_picture = Column(String(500), nullable=True)
    auth_provider = Column(String(50), default="local")  # "local" or "google"
    
    # GPT API Key field (encrypted)
    gpt_api_key_encrypted = Column(Text, nullable=True)
    
    # Encryption key for API keys (generated per app instance)
    _encryption_key = None
    
    @staticmethod
    def hash_password(password: str) -> str:
        """Hash password using SHA256"""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def verify_password(self, password: str) -> bool:
        """Verify password against hash"""
        if not self.password_hash:
            return False  # OAuth users don't have password
        return self.password_hash == self.hash_password(password)
    
    @classmethod
    def _get_encryption_key(cls):
        """Get or create encryption key for API keys"""
        if cls._encryption_key is None:
            # Use a fixed key for this application instance
            # In production, this should be stored securely
            cls._encryption_key = Fernet.generate_key()
        return cls._encryption_key
    
    def set_gpt_api_key(self, api_key: str) -> None:
        """Encrypt and store GPT API key"""
        if api_key:
            cipher = Fernet(self._get_encryption_key())
            encrypted_key = cipher.encrypt(api_key.encode())
            self.gpt_api_key_encrypted = base64.b64encode(encrypted_key).decode()
        else:
            self.gpt_api_key_encrypted = None
    
    def get_gpt_api_key(self) -> Optional[str]:
        """Decrypt and return GPT API key"""
        if not self.gpt_api_key_encrypted:
            return None
        
        try:
            cipher = Fernet(self._get_encryption_key())
            encrypted_key = base64.b64decode(self.gpt_api_key_encrypted.encode())
            return cipher.decrypt(encrypted_key).decode()
        except Exception as e:
            print(f"Error decrypting API key: {e}")
            return None
    
    def has_gpt_api_key(self) -> bool:
        """Check if admin has a GPT API key configured"""
        return self.gpt_api_key_encrypted is not None
    
    @classmethod
    def create_admin(cls, username: str, email: str, password: str = None, full_name: str = None, 
                     is_super_admin: bool = False, google_id: str = None, profile_picture: str = None):
        """Create a new admin user"""
        auth_provider = "google" if google_id else "local"
        password_hash = cls.hash_password(password) if password else None
        
        return cls(
            username=username,
            email=email,
            password_hash=password_hash,
            full_name=full_name,
            is_super_admin=is_super_admin,
            google_id=google_id,
            profile_picture=profile_picture,
            auth_provider=auth_provider
        )
    
    @classmethod
    def create_from_google(cls, google_user_info: dict, is_super_admin: bool = False):
        """Create admin user from Google OAuth info"""
        return cls.create_admin(
            username=google_user_info.get("email").split("@")[0],  # Use email prefix as username
            email=google_user_info.get("email"),
            full_name=google_user_info.get("name"),
            google_id=google_user_info.get("sub"),
            profile_picture=google_user_info.get("picture"),
            is_super_admin=is_super_admin
        )

class AdminSession(Base):
    __tablename__ = "admin_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    admin_id = Column(Integer, nullable=False, index=True)
    session_token = Column(String(255), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.now)
    expires_at = Column(DateTime, nullable=False)
    last_accessed = Column(DateTime, default=datetime.now)
    is_active = Column(Boolean, default=True)
    
    @classmethod
    def create_session(cls, admin_id: int, duration_hours: int = 24):
        """Create a new admin session"""
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now() + timedelta(hours=duration_hours)
        
        return cls(
            admin_id=admin_id,
            session_token=token,
            expires_at=expires_at
        )
    
    def is_expired(self) -> bool:
        """Check if session has expired"""
        return datetime.now() > self.expires_at
    
    def refresh_session(self):
        """Update last accessed time"""
        self.last_accessed = datetime.now()