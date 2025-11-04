from datetime import datetime, timedelta
from typing import Optional
import uuid
import secrets
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.orm import relationship
from database.db import Base

class URLInjectionRequest(Base):
    __tablename__ = "url_injection_requests"
    
    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(String(255), unique=True, nullable=False, index=True)
    url = Column(Text, nullable=False)
    requester_email = Column(String(255), nullable=False)
    confirmation_token = Column(String(255), unique=True, nullable=False)
    is_confirmed = Column(Boolean, default=False)
    is_processed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)
    confirmed_at = Column(DateTime, nullable=True)
    processed_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=False)
    
    # Enhanced fields for admin management
    priority = Column(String(20), default="normal")  # normal, high, urgent
    notes = Column(Text, nullable=True)
    processing_status = Column(String(50), default="pending")  # pending, processing, completed, failed, removed
    content_type = Column(String(100), nullable=True)
    title = Column(String(500), nullable=True)
    processed_by = Column(String(255), nullable=True)  # Admin who processed it
    admin_created = Column(Boolean, default=False)  # Whether created through admin panel
    admin_username = Column(String(255), nullable=True)  # Admin who created the request
    
    # User tracking for dashboard
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # Link to user who submitted
    description = Column(Text, nullable=True)  # User-provided description
    status = Column(String(20), default="pending")  # pending, approved, rejected, processing
    firm_id = Column(Integer, ForeignKey("firms.id"), nullable=True)  # Associated firm
    
    # Relationships
    firm = relationship("Firm", back_populates="url_requests")
    
    @classmethod
    def create_request(cls, url: str, email: str, priority: str = "normal", notes: str = "") -> 'URLInjectionRequest':
        """Create a new URL injection request with confirmation token"""
        request_id = str(uuid.uuid4())
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now() + timedelta(hours=24)  # 24 hour expiry
        
        return cls(
            request_id=request_id,
            url=url,
            requester_email=email,
            confirmation_token=token,
            expires_at=expires_at,
            priority=priority,
            notes=notes
        )
    
    @classmethod
    def create_user_request(cls, url: str, user_id: int, email: str, description: str = "") -> 'URLInjectionRequest':
        """Create a new URL injection request from user dashboard"""
        request_id = str(uuid.uuid4())
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now() + timedelta(hours=72)  # 72 hour expiry for user requests
        
        return cls(
            request_id=request_id,
            url=url,
            requester_email=email,
            confirmation_token=token,
            expires_at=expires_at,
            user_id=user_id,
            description=description,
            is_confirmed=True,  # User requests are auto-confirmed
            confirmed_at=datetime.now(),
            status="pending"
        )
    
    def is_expired(self) -> bool:
        """Check if the request has expired"""
        return datetime.now() > self.expires_at
    
    def confirm(self) -> bool:
        """Confirm the request if not expired"""
        if self.is_expired() or self.is_confirmed:
            return False
        
        self.is_confirmed = True
        self.confirmed_at = datetime.now()
        return True
    
    def mark_processed(self, processed_by: str = None) -> bool:
        """Mark the request as processed"""
        if not self.is_confirmed or self.is_processed:
            return False
        
        self.is_processed = True
        self.processed_at = datetime.now()
        self.processing_status = "completed"
        if processed_by:
            self.processed_by = processed_by
        return True

    def mark_failed(self, processed_by: str = None) -> bool:
        """Mark the request as failed"""
        self.processing_status = "failed"
        self.processed_at = datetime.now()
        if processed_by:
            self.processed_by = processed_by
        return True

    def set_processing(self) -> bool:
        """Mark the request as currently being processed"""
        if not self.is_confirmed:
            return False
        
        self.processing_status = "processing"
        return True
    def mark_processed(self) -> None:
        """Mark the request as processed"""
        self.is_processed = True
        self.processed_at = datetime.now()