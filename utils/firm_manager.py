# utils/firm_manager.py

import re
from urllib.parse import urlparse
from sqlalchemy.orm import Session
from model.models import Firm
from database.db import SessionLocal

class FirmManager:
    """Centralized firm management to prevent duplicates and ensure consistency"""
    
    @staticmethod
    def normalize_firm_name(url_or_name: str) -> str:
        """
        Normalize firm name from URL or title to ensure consistency.
        This prevents duplicate firms with similar names.
        """
        if not url_or_name:
            return "Unknown"
        
        # If it's a URL, extract domain
        if url_or_name.startswith(('http://', 'https://')):
            parsed = urlparse(url_or_name)
            domain = parsed.netloc.lower()
        else:
            domain = url_or_name.lower()
        
        # Remove common prefixes
        domain = re.sub(r'^www\.', '', domain)
        
        # Remove common TLDs and keep main name
        # For domains like "example.com" -> "example"
        # For domains like "subdomain.example.com" -> "example" 
        parts = domain.split('.')
        
        if len(parts) >= 2:
            # Take the main domain name (second to last part for most cases)
            # Handle cases like: www.example.com, api.example.com, example.com
            if len(parts) == 2:
                main_part = parts[0]  # example.com -> example
            elif len(parts) >= 3:
                # subdomain.example.com -> example
                main_part = parts[-2]  # Take second to last
            else:
                main_part = parts[0]
        else:
            main_part = parts[0]
        
        # Clean up the main part
        main_part = re.sub(r'[^a-zA-Z0-9\-]', '', main_part)
        
        # Capitalize first letter for consistency
        return main_part.capitalize() if main_part else "Unknown"
    
    @staticmethod
    def get_or_create_firm(url: str, title: str = None, db: Session = None) -> int:
        """
        Get existing firm or create new one with consistent naming.
        Returns firm_id.
        
        Args:
            url: The website URL
            title: Optional website title (fallback to domain if provided)
            db: Database session (creates new one if not provided)
        
        Returns:
            int: The firm ID
        """
        should_close_db = False
        if db is None:
            db = SessionLocal()
            should_close_db = True
        
        try:
            # Extract domain for fallback
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            
            # Determine firm name priority:
            # 1. Use normalized domain from URL (most reliable)
            # 2. If title provided and looks like company name, use it
            # 3. Fallback to domain
            
            firm_name = FirmManager.normalize_firm_name(url)
            
            # If title is provided and seems like a better name, use it
            if title and title.strip() and len(title.strip()) > 0:
                title_normalized = FirmManager.normalize_firm_name(title)
                # Use title if it's not just the domain and seems meaningful
                if (title_normalized != firm_name and 
                    len(title_normalized) > 2 and 
                    not title_normalized.lower() in ['home', 'index', 'welcome']):
                    firm_name = title_normalized
            
            # Check for existing firm with exact name match (case insensitive)
            existing_firm = db.query(Firm).filter(
                Firm.name.ilike(firm_name)
            ).first()
            
            if existing_firm:
                return existing_firm.id
            
            # Check for similar firm names to prevent duplicates
            # Look for firms with similar domain
            domain_base = FirmManager.normalize_firm_name(domain)
            similar_firm = db.query(Firm).filter(
                Firm.name.ilike(f"%{domain_base}%")
            ).first()
            
            if similar_firm:
                return similar_firm.id
            
            # Create new firm
            new_firm = Firm(name=firm_name)
            db.add(new_firm)
            db.flush()  # Get ID without full commit
            
            print(f"[FirmManager] Created new firm: {firm_name} (from {url})")
            return new_firm.id
            
        except Exception as e:
            print(f"[FirmManager] Error managing firm for {url}: {e}")
            # Fallback: create with domain name
            try:
                fallback_name = FirmManager.normalize_firm_name(url)
                fallback_firm = Firm(name=fallback_name)
                db.add(fallback_firm)
                db.flush()
                return fallback_firm.id
            except Exception as fallback_error:
                print(f"[FirmManager] Fallback failed: {fallback_error}")
                raise
        finally:
            if should_close_db:
                try:
                    db.commit()
                except:
                    db.rollback()
                    raise
                finally:
                    db.close()
    
    @staticmethod
    def merge_duplicate_firms(db: Session = None) -> int:
        """
        Find and merge duplicate firms that might have been created.
        Returns number of duplicates merged.
        """
        should_close_db = False
        if db is None:
            db = SessionLocal()
            should_close_db = True
        
        try:
            firms = db.query(Firm).all()
            merged_count = 0
            firms_to_remove = []
            
            # Group firms by normalized name
            firm_groups = {}
            for firm in firms:
                normalized = FirmManager.normalize_firm_name(firm.name)
                if normalized not in firm_groups:
                    firm_groups[normalized] = []
                firm_groups[normalized].append(firm)
            
            # Merge duplicates
            for normalized_name, firm_list in firm_groups.items():
                if len(firm_list) > 1:
                    # Keep the first (oldest) firm
                    primary_firm = firm_list[0]
                    duplicates = firm_list[1:]
                    
                    print(f"[FirmManager] Merging {len(duplicates)} duplicate firms for '{normalized_name}'")
                    
                    # Move all websites from duplicates to primary
                    for duplicate_firm in duplicates:
                        for website in duplicate_firm.websites:
                            website.firm_id = primary_firm.id
                        
                        firms_to_remove.append(duplicate_firm)
                        merged_count += 1
            
            # Remove duplicate firms
            for firm in firms_to_remove:
                db.delete(firm)
            
            if merged_count > 0:
                db.commit()
                print(f"[FirmManager] Successfully merged {merged_count} duplicate firms")
            
            return merged_count
            
        except Exception as e:
            if db:
                db.rollback()
            print(f"[FirmManager] Error merging firms: {e}")
            return 0
        finally:
            if should_close_db and db:
                db.close()

# Convenience instance
firm_manager = FirmManager()