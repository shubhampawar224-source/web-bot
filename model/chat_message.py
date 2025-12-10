from sqlalchemy import Column, Integer, String, Text, DateTime
from datetime import datetime
# Assuming your db connection file is named 'database/db.py'
from database.db import Base 
from zoneinfo import ZoneInfo

def get_cst_now():
    return datetime.now(ZoneInfo("America/Chicago"))


class ChatMessage(Base):
    __tablename__ = "voice_chat_history"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, index=True, nullable=False)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=get_cst_now)

    def __repr__(self):
        return f"<ChatMessage(session={self.session_id}, role={self.role})>"