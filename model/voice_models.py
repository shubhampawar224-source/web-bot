from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from database.db import Base


class Firm(Base):
    __tablename__ = "firms"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.now)

    # Relationships
    websites = relationship("Website", back_populates="firm", cascade="all, delete-orphan")


class Website(Base):
    __tablename__ = "websites"

    id = Column(Integer, primary_key=True, index=True)
    domain = Column(String(255), nullable=False)
    base_url = Column(String(500), unique=True, nullable=False)
    firm_id = Column(Integer, ForeignKey("firms.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.now)

    firm = relationship("Firm", back_populates="websites")
    pages = relationship("Page", back_populates="website", cascade="all, delete-orphan")
    links = relationship("Link", back_populates="website", cascade="all, delete-orphan")


class Page(Base):
    __tablename__ = "pages"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String(1000), unique=True, nullable=False)
    title = Column(String(500))
    meta_description = Column(Text)
    content = Column(Text)
    scraped_at = Column(DateTime, default=datetime.now)
    website_id = Column(Integer, ForeignKey("websites.id"), nullable=False)

    website = relationship("Website", back_populates="pages")


class Link(Base):
    __tablename__ = "links"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500))
    url = Column(String(1000))
    website_id = Column(Integer, ForeignKey("websites.id"), nullable=False)
    page_id = Column(Integer, ForeignKey("pages.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    website = relationship("Website", back_populates="links")
    page = relationship("Page")
