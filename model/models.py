from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from database.db import Base


class Firm(Base):
    __tablename__ = "firms"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    websites = relationship("Website", back_populates="firm")
    

class Website(Base):
    __tablename__ = "websites"

    id = Column(Integer, primary_key=True, index=True)
    domain = Column(String(255), nullable=False)
    base_url = Column(String(500), unique=True, nullable=False)
    firm_id = Column(Integer, ForeignKey("firms.id"))
    created_at = Column(DateTime, default=datetime.now)

    scraped_data = Column(JSON, default={})

    firm = relationship("Firm", back_populates="websites")

    def add_scraped_data(self, about_dict, links_list):
        """Merge scraped data into JSON field"""
        self.scraped_data = {
            "about": about_dict,
            "links": links_list
        }
