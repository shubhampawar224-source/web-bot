# voice_config/services/contact_service.py
from database.db import SessionLocal 
from model.models import Contact
from datetime import datetime, timezone
import traceback

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

def save_contact_to_db(first_name: str, last_name: str, phone: str, email: str = None):
    print(f"📝 DB Function Called with: fname='{first_name}', lname='{last_name}', phone='{phone}', email='{email}'") # Debug Log
    
    db = SessionLocal()
    
    try:
        # Timezone setup
        utc_now = datetime.now(timezone.utc)
        try:
            cst_now = utc_now.astimezone(ZoneInfo("America/Chicago"))
            print(f"🕒 Using CST time: {cst_now}")
        except Exception as tz_err:
            print(f"⚠️ Timezone error: {tz_err}, using UTC")
            cst_now = utc_now # Fallback if timezone fails
        
        # ⭐ CRITICAL MAPPING HERE ⭐
        # Function arg 'first_name' -> Model column 'fname'
        # Function arg 'phone'      -> Model column 'phone_number'
        new_contact = Contact(
            fname=first_name,       # Mapping 1
            lname=last_name,        # Mapping 2
            phone_number=phone,     # Mapping 3 (Bahut zaroori)
            email=email,
            created_at=cst_now
        )
        
        print(f"💾 Attempting to save contact: {new_contact.fname} {new_contact.lname}")
        
        db.add(new_contact)
        db.commit()
        db.refresh(new_contact)
        
        
        print(f"✅ Data Saved Successfully! ID: {new_contact.id}, Phone: {new_contact.phone_number}")
        return True

    except Exception as e:
        print(f"❌ DB Error: {e}")
        traceback.print_exc()
        db.rollback()
        return False

    finally:
        db.close()
        print(f"🔒 Database connection closed")