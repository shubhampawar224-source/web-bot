from database.db import SessionLocal 
from model.models import Contact

def save_contact_to_db(first_name: str, last_name: str, phone: str, email: str = None):
    db = SessionLocal()
    from datetime import datetime
    try:
        # Use CST timezone for created_at
        from zoneinfo import ZoneInfo
        cst_now = datetime.now(ZoneInfo("America/Chicago"))
        new_contact = Contact(
            fname=first_name,
            lname=last_name,
            phone_number=phone,
            email=email,
            created_at=cst_now
        )
        db.add(new_contact)
        db.commit()
        db.refresh(new_contact)
        print(f"✅ Data Saved: {first_name} {last_name} at {cst_now}")
        return True
    except Exception as e:
        print(f"❌ DB Error: {e}")
        db.rollback()
        return False
    finally:
        db.close()