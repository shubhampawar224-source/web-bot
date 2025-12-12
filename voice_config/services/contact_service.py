from database.db import SessionLocal 
from model.models import Contact

def save_contact_to_db(first_name: str, last_name: str, phone: str, email: str = None):
    db = SessionLocal()
    try:
        new_contact = Contact(
            fname=first_name,
            lname=last_name,
            phone_number=phone,
            email=email
        )
        db.add(new_contact)
        db.commit()
        db.refresh(new_contact)
        print(f"✅ Data Saved: {first_name} {last_name}")
        return True
    except Exception as e:
        print(f"❌ DB Error: {e}")
        db.rollback()
        return False
    finally:
        db.close()