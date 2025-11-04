#!/usr/bin/env python3
"""
Script to populate firm_id for existing URL injection requests
"""

from database.db import SessionLocal
from model.url_injection_models import URLInjectionRequest
from model.models import Firm
from utils.url_processing_service import URLProcessingService
from urllib.parse import urlparse

def populate_firm_ids():
    """Populate firm_id for existing URL requests that don't have one"""
    db = SessionLocal()
    url_service = URLProcessingService()
    
    try:
        # Get all URL requests without firm_id
        urls_without_firm = db.query(URLInjectionRequest).filter(
            URLInjectionRequest.firm_id.is_(None)
        ).all()
        
        print(f"Found {len(urls_without_firm)} URLs without firm_id")
        
        for url_request in urls_without_firm:
            print(f"Processing URL: {url_request.url}")
            
            # Get or create firm for this URL
            firm_id = url_service.get_firm_from_url(url_request.url, db)
            
            if firm_id:
                url_request.firm_id = firm_id
                firm = db.query(Firm).filter(Firm.id == firm_id).first()
                print(f"  -> Assigned to firm: {firm.name if firm else 'Unknown'} (ID: {firm_id})")
            else:
                print(f"  -> Could not determine firm for URL")
        
        db.commit()
        print("✅ Firm IDs populated successfully!")
        
        # Show summary
        print("\n--- Summary ---")
        firms_with_urls = db.query(Firm).join(URLInjectionRequest).distinct().all()
        for firm in firms_with_urls:
            url_count = db.query(URLInjectionRequest).filter(URLInjectionRequest.firm_id == firm.id).count()
            print(f"{firm.name}: {url_count} URLs")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    populate_firm_ids()