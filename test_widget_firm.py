#!/usr/bin/env python3
"""
Test script to debug widget firm detection
"""

from database.db import SessionLocal
from model.url_injection_models import URLInjectionRequest
from model.models import Firm

def test_widget_firm_detection():
    """Test the widget firm detection logic"""
    db = SessionLocal()
    
    try:
        # Get all completed URL requests
        completed_urls = db.query(URLInjectionRequest).filter(
            URLInjectionRequest.status == "completed"
        ).all()
        
        print(f"Found {len(completed_urls)} completed URLs:")
        
        for url in completed_urls:
            print(f"\nURL: {url.url}")
            print(f"  ID: {url.id}")
            print(f"  Request ID: {url.request_id}")
            print(f"  Firm ID: {url.firm_id}")
            print(f"  Status: {url.status}")
            
            if url.firm_id:
                firm = db.query(Firm).filter(Firm.id == url.firm_id).first()
                print(f"  Firm Name: {firm.name if firm else 'Not found'}")
            else:
                print(f"  Firm Name: None")
                
        # Test the firm-info endpoint logic
        print("\n" + "="*50)
        print("Testing firm-info endpoint logic:")
        
        if completed_urls:
            test_url = completed_urls[0]
            print(f"\nTesting with URL ID: {test_url.id}")
            
            # Simulate the endpoint logic
            url_id_list = [test_url.id]
            url_request = db.query(URLInjectionRequest).filter(
                URLInjectionRequest.id.in_(url_id_list),
                URLInjectionRequest.status == "completed"
            ).first()
            
            if url_request:
                print(f"✅ Found URL request: {url_request.url}")
                if url_request.firm_id:
                    firm = db.query(Firm).filter(Firm.id == url_request.firm_id).first()
                    if firm:
                        print(f"✅ Firm detected: {firm.name}")
                    else:
                        print(f"❌ Firm ID exists but firm not found")
                else:
                    print(f"⚠️ No firm_id assigned to this URL")
            else:
                print(f"❌ No completed URL found with this ID")
                
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    test_widget_firm_detection()