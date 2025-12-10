from datetime import datetime
from sqlalchemy.orm import Session
from database.db import SessionLocal
# Make sure model/chat_models.py exists and has ChatMessage class
from model.chat_message import ChatMessage 

class DbChatMemory:
    def __init__(self, session_id):
        self.session_id = session_id

    def add_message(self, role, content):
        """
        Message ko database me save karta hai.
        Run this in a thread to avoid blocking.
        """
        if not content:
            return
        
        db: Session = SessionLocal()
        try:
            new_msg = ChatMessage(
                session_id=self.session_id,
                role=role,
                content=content,
                timestamp=datetime.utcnow()
            )
            db.add(new_msg)
            db.commit()
            # db.refresh(new_msg) # Optional, usually not needed for logs
        except Exception as e:
            print(f"❌ DB Save Error: {e}")
        finally:
            db.close()

    def get_context_summary(self, limit=6):
        """
        Pichli baatein (Last N messages) fetch karta hai 
        taaki AI ko context yaad rahe.
        """
        db: Session = SessionLocal()
        try:
            # Last 'limit' messages nikalo (Newest first)
            messages = (
                db.query(ChatMessage)
                .filter(ChatMessage.session_id == self.session_id)
                .order_by(ChatMessage.timestamp.desc())
                .limit(limit)
                .all()
            )
            
            # Wapas seedha karo (Oldest to Newest) taaki flow sahi rahe
            messages.reverse()
            
            if not messages:
                return ""
            
            # String format: "USER: Hello\nASSISTANT: Hi there"
            return "\n".join([f"{m.role.upper()}: {m.content}" for m in messages])
            
        except Exception as e:
            print(f"❌ DB Load Error: {e}")
            return ""
        finally:
            db.close()