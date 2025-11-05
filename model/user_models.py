from datetime import datetime, timedelta
from typing import Optional
import secrets
import hashlib
import base64
from cryptography.fernet import Fernet
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text
from database.db import Base
import os

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)  # For email verification if needed
    created_at = Column(DateTime, default=datetime.now)
    last_login = Column(DateTime, nullable=True)
    
    # Optional profile fields
    phone = Column(String(20), nullable=True)
    date_of_birth = Column(DateTime, nullable=True)
    profile_picture = Column(String(500), nullable=True)
    
    # GPT API Key field (encrypted)
    gpt_api_key_encrypted = Column(Text, nullable=True)
    
    # Encryption key for API keys (generated per app instance)
    _encryption_key = None
    
    @classmethod
    def _get_encryption_key(cls):
        """Get or create encryption key for API keys"""
        if cls._encryption_key is None:
            # Try to get key from environment or generate new one
            key_env = os.getenv("ENCRYPTION_KEY")
            if key_env:
                cls._encryption_key = key_env.encode()
            else:
                # Generate a new key (in production, this should be stored securely)
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
            decrypted_key = cipher.decrypt(encrypted_key).decode()
            return decrypted_key
        except Exception as e:
            print(f"Error decrypting API key: {e}")
            return None
    
    @property
    def has_gpt_api_key(self) -> bool:
        """Check if user has a GPT API key configured"""
        return self.gpt_api_key_encrypted is not None
    
    @staticmethod
    def hash_password(password: str) -> str:
        """Hash password using SHA256"""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def verify_password(self, password: str) -> bool:
        """Verify password against hash"""
        return self.password_hash == self.hash_password(password)
    
    @property
    def full_name(self) -> str:
        """Get full name"""
        return f"{self.first_name} {self.last_name}"
    
    @classmethod
    def create_user(cls, first_name: str, last_name: str, email: str, password: str, 
                    phone: str = None, date_of_birth: datetime = None):
        """Create a new user"""
        return cls(
            first_name=first_name,
            last_name=last_name,
            email=email,
            password_hash=cls.hash_password(password),
            phone=phone,
            date_of_birth=date_of_birth
        )

class UserSession(Base):
    __tablename__ = "user_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    session_token = Column(String(255), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.now)
    expires_at = Column(DateTime, nullable=False)
    last_accessed = Column(DateTime, default=datetime.now)
    is_active = Column(Boolean, default=True)
    device_info = Column(String(500), nullable=True)  # Store browser/device info
    ip_address = Column(String(45), nullable=True)  # Store IP address
    
    @classmethod
    def create_session(cls, user_id: int, duration_hours: int = 168, device_info: str = None, ip_address: str = None):
        """Create a new user session (default 7 days)"""
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now() + timedelta(hours=duration_hours)
        
        return cls(
            user_id=user_id,
            session_token=token,
            expires_at=expires_at,
            device_info=device_info,
            ip_address=ip_address
        )
    
    def is_expired(self) -> bool:
        """Check if session has expired"""
        return datetime.now() > self.expires_at
    
    def refresh_session(self):
        """Update last accessed time"""
        self.last_accessed = datetime.now()
    
    def extend_session(self, hours: int = 168):
        """Extend session expiry"""
        self.expires_at = datetime.now() + timedelta(hours=hours)
        self.refresh_session()