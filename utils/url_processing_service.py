# utils/url_processing_service.py

import asyncio
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse
from sqlalchemy.orm import Session
from database.db import SessionLocal
from model.url_injection_models import URLInjectionRequest
from model.models import Website, Firm
from utils.scraper import build_about
from utils.vector_store import chunk_text, add_text_chunks_to_collection
from utils.firm_manager import FirmManager
import logging

logger = logging.getLogger(__name__)

class URLProcessingService:
    """Service to handle URL processing, scraping, and vector storage"""
    
    def __init__(self):
        self.max_retries = 3
    
    def get_firm_from_url(self, url: str, db: Session) -> Optional[int]:
        """Extract domain from URL and find or create matching firm using centralized manager"""
        try:
            return FirmManager.get_or_create_firm(url=url, db=db)
        except Exception as e:
            logger.error(f"Error determining firm from URL {url}: {e}")
            return None
    
    async def process_url_request(self, request_id: str, processed_by: str = None) -> Tuple[bool, str]:
        """Process a confirmed URL request by scraping and storing in vector DB"""
        db: Session = SessionLocal()
        try:
            # Get the URL request
            url_request = db.query(URLInjectionRequest).filter(
                URLInjectionRequest.request_id == request_id
            ).first()
            
            if not url_request:
                return False, "URL request not found"
            
            if not url_request.is_confirmed:
                return False, "URL request not confirmed"
            
            if url_request.is_processed:
                return False, "URL request already processed"
            
            # Determine and set firm_id if not already set
            if not url_request.firm_id:
                firm_id = self.get_firm_from_url(url_request.url, db)
                if firm_id:
                    url_request.firm_id = firm_id
            
            # Check if URL already exists in database
            existing_site = db.query(Website).filter(
                Website.base_url == url_request.url
            ).first()
            
            if existing_site:
                firm_name = existing_site.firm.name if existing_site.firm else "Unknown"
                url_request.processing_status = "failed"
                url_request.notes = f"URL already exists in database (Firm: {firm_name})"
                db.commit()
                return False, f"URL already exists in database (Firm: {firm_name})"
            
            # Update status to processing
            url_request.processing_status = "processing"
            url_request.processed_by = processed_by
            db.commit()
            
            try:
                # Scrape the URL
                logger.info(f"Starting to scrape URL: {url_request.url}")
                about_obj = await build_about(url_request.url)
                
                if not about_obj:
                    url_request.processing_status = "failed"
                    url_request.notes = "Failed to scrape content from URL"
                    db.commit()
                    return False, "Failed to scrape content from URL"
                
                full_text = about_obj.get("full_text", "").strip()
                if not full_text:
                    url_request.processing_status = "failed"
                    url_request.notes = "No text content found on webpage"
                    db.commit()
                    return False, "No text content found on webpage"
                
                # Process and store in vector database
                chunks = chunk_text(full_text)
                metadata = {
                    "type": "user_website",
                    "url": url_request.url,
                    "firm_name": about_obj.get("firm_name"),
                    "user_id": url_request.user_id,
                    "user_email": url_request.requester_email,
                    "description": url_request.description,
                    "request_id": request_id
                }
                
                add_text_chunks_to_collection(chunks, metadata)
                
                # Mark as completed
                url_request.is_processed = True
                url_request.processing_status = "completed"
                url_request.status = "approved"
                url_request.notes = f"Successfully processed {len(chunks)} content chunks"
                url_request.content_type = "website"
                url_request.title = about_obj.get("firm_name", "")
                
                # Import datetime here to avoid circular imports
                from datetime import datetime
                url_request.processed_at = datetime.now()
                
                db.commit()
                
                logger.info(f"Successfully processed URL: {url_request.url} with {len(chunks)} chunks")
                return True, f"Successfully processed {len(chunks)} content chunks"
                
            except Exception as scrape_error:
                logger.error(f"Error processing URL {url_request.url}: {scrape_error}")
                url_request.processing_status = "failed"
                url_request.notes = f"Processing error: {str(scrape_error)}"
                db.commit()
                return False, f"Processing error: {str(scrape_error)}"
                
        except Exception as e:
            logger.error(f"Database error processing URL request {request_id}: {e}")
            db.rollback()
            return False, f"Database error: {str(e)}"
        finally:
            db.close()
    
    def approve_url_request(self, request_id: str, admin_username: str = None) -> Tuple[bool, str]:
        """Approve a user's URL request for processing"""
        db: Session = SessionLocal()
        try:
            url_request = db.query(URLInjectionRequest).filter(
                URLInjectionRequest.request_id == request_id
            ).first()
            
            if not url_request:
                return False, "URL request not found"
            
            if url_request.status == "approved":
                return False, "URL request already approved"
            
            url_request.status = "approved"
            url_request.processed_by = admin_username
            
            # Import datetime here
            from datetime import datetime
            url_request.confirmed_at = datetime.now()
            url_request.is_confirmed = True
            
            db.commit()
            return True, "URL request approved successfully"
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error approving URL request {request_id}: {e}")
            return False, f"Error approving request: {str(e)}"
        finally:
            db.close()
    
    def reject_url_request(self, request_id: str, reason: str = None, admin_username: str = None) -> Tuple[bool, str]:
        """Reject a user's URL request"""
        db: Session = SessionLocal()
        try:
            url_request = db.query(URLInjectionRequest).filter(
                URLInjectionRequest.request_id == request_id
            ).first()
            
            if not url_request:
                return False, "URL request not found"
            
            url_request.status = "rejected"
            url_request.processing_status = "rejected"
            url_request.processed_by = admin_username
            url_request.notes = reason or "Rejected by admin"
            
            # Import datetime here
            from datetime import datetime
            url_request.processed_at = datetime.now()
            
            db.commit()
            return True, "URL request rejected successfully"
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error rejecting URL request {request_id}: {e}")
            return False, f"Error rejecting request: {str(e)}"
        finally:
            db.close()

# Global instance
url_processing_service = URLProcessingService()