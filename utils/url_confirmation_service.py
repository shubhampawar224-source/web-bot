import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from database.db import SessionLocal
from model.url_injection_models import URLInjectionRequest

load_dotenv(override=True)

class URLConfirmationService:
    def __init__(self):
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER")
        self.smtp_pass = os.getenv("SMTP_PASS")
        self.from_email = os.getenv("FROM_EMAIL")
        self.base_url = os.getenv("WIDGET_BASE_URL", "http://127.0.0.1:8000")
        
    def send_confirmation_email(self, request: URLInjectionRequest) -> bool:
        """Send confirmation email to the requester"""
        try:
            confirmation_url = f"{self.base_url}/confirm-url-injection/{request.confirmation_token}"
            
            # Create email content
            subject = "🔐 Confirm URL Injection Request"
            
            html_body = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background-color: #4a90e2; color: white; padding: 20px; border-radius: 8px 8px 0 0; }}
                    .content {{ background-color: #f9f9f9; padding: 30px; border-radius: 0 0 8px 8px; }}
                    .button {{ display: inline-block; background-color: #4a90e2; color: white; padding: 12px 30px; 
                              text-decoration: none; border-radius: 5px; margin: 20px 0; }}
                    .button:hover {{ background-color: #357abd; }}
                    .url-box {{ background-color: #e3f2fd; padding: 15px; border-radius: 5px; margin: 15px 0; 
                               border-left: 4px solid #4a90e2; }}
                    .warning {{ color: #e74c3c; font-weight: bold; }}
                    .footer {{ text-align: center; color: #666; font-size: 12px; margin-top: 30px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h2>🔐 URL Injection Authorization Required</h2>
                    </div>
                    <div class="content">
                        <h3>Hello,</h3>
                        <p>Someone has requested to inject the following URL into our web assistant system:</p>
                        
                        <div class="url-box">
                            <strong>🌐 Requested URL:</strong><br>
                            <code>{request.url}</code>
                        </div>
                        
                        <p><strong>📧 Requester Email:</strong> {request.requester_email}</p>
                        <p><strong>🕒 Request Time:</strong> {request.created_at.strftime('%Y-%m-%d %H:%M:%S')}</p>
                        
                        <div class="warning">
                            ⚠️ Only click the button below if you authorized this request!
                        </div>
                        
                        <p>If you approve this URL injection, click the confirmation button:</p>
                        
                        <a href="{confirmation_url}" class="button">
                            ✅ Confirm URL Injection
                        </a>
                        
                        <p><strong>⏰ This link expires in 24 hours.</strong></p>
                        
                        <hr>
                        
                        <h4>🛡️ Security Information:</h4>
                        <ul>
                            <li>This URL will be scraped and its content added to our AI assistant's knowledge base</li>
                            <li>Only authorize URLs from trusted sources</li>
                            <li>If you didn't request this, please ignore this email</li>
                            <li>The link will expire automatically after 24 hours</li>
                        </ul>
                        
                        <p>If you have any questions, please contact our support team.</p>
                        
                        <div class="footer">
                            <p>This is an automated email from Web Assistant System<br>
                            Request ID: {request.request_id}</p>
                        </div>
                    </div>
                </div>
            </body>
            </html>
            """
            
            text_body = f"""
            URL Injection Authorization Required
            
            Hello,
            
            Someone has requested to inject the following URL into our web assistant system:
            
            Requested URL: {request.url}
            Requester Email: {request.requester_email}
            Request Time: {request.created_at.strftime('%Y-%m-%d %H:%M:%S')}
            
            WARNING: Only confirm if you authorized this request!
            
            To confirm this URL injection, click the following link:
            {confirmation_url}
            
            This link expires in 24 hours.
            
            Security Information:
            - This URL will be scraped and its content added to our AI assistant's knowledge base
            - Only authorize URLs from trusted sources
            - If you didn't request this, please ignore this email
            - The link will expire automatically after 24 hours
            
            Request ID: {request.request_id}
            """
            
            # Create message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.from_email
            msg["To"] = request.requester_email
            
            # Attach both text and HTML versions
            msg.attach(MIMEText(text_body, "plain"))
            msg.attach(MIMEText(html_body, "html"))
            
            # Send email
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_pass)
                server.send_message(msg)
            
            print(f"✅ Confirmation email sent to {request.requester_email}")
            print(f"📧 Email details - Request ID: {request.request_id}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to send confirmation email: {e}")
            return False
    
    def create_and_send_request(self, url: str, email: str) -> Optional[URLInjectionRequest]:
        """Create a new URL injection request and send confirmation email"""
        db: Session = SessionLocal()
        try:
            # Check if URL already exists
            from model.models import Website
            existing_site = db.query(Website).filter(Website.base_url == url).first()
            if existing_site:
                return None  # URL already exists
            
            # Check for pending requests for the same URL
            existing_request = db.query(URLInjectionRequest).filter(
                URLInjectionRequest.url == url,
                URLInjectionRequest.is_processed == False
            ).first()
            
            if existing_request and not existing_request.is_expired():
                return None  # Pending request already exists
            
            # Create new request
            request = URLInjectionRequest.create_request(url, email)
            db.add(request)
            db.commit()
            db.refresh(request)
            
            print(f"🔧 Created URL injection request - ID: {request.request_id}")
            print(f"🔧 Request details - URL: {request.url}, Email: {request.requester_email}")
            
            # Send confirmation email
            if self.send_confirmation_email(request):
                return request
            else:
                # If email fails, delete the request
                db.delete(request)
                db.commit()
                return None
                
        except Exception as e:
            db.rollback()
            print(f"Error creating URL injection request: {e}")
            return None
        finally:
            db.close()
    
    def confirm_request(self, token: str) -> tuple[bool, str]:
        """Confirm a URL injection request using the token"""
        db: Session = SessionLocal()
        try:
            request = db.query(URLInjectionRequest).filter(
                URLInjectionRequest.confirmation_token == token
            ).first()
            
            if not request:
                return False, "Invalid confirmation token"
            
            if request.is_expired():
                return False, "Confirmation link has expired"
            
            if request.is_confirmed:
                if request.is_processed:
                    return False, "This URL has already been processed"
                else:
                    return False, "This request has already been confirmed but is pending processing"
            
            # Confirm the request
            if request.confirm():
                db.commit()
                return True, "URL injection request confirmed successfully"
            else:
                return False, "Failed to confirm request"
                
        except Exception as e:
            db.rollback()
            print(f"Error confirming request: {e}")
            return False, "An error occurred while confirming the request"
        finally:
            db.close()
    
    def get_pending_confirmed_requests(self) -> list[URLInjectionRequest]:
        """Get all confirmed but unprocessed requests"""
        db: Session = SessionLocal()
        try:
            requests = db.query(URLInjectionRequest).filter(
                URLInjectionRequest.is_confirmed == True,
                URLInjectionRequest.is_processed == False
            ).all()
            return requests
        finally:
            db.close()
    
    def mark_request_processed(self, request_id: str) -> bool:
        """Mark a request as processed"""
        db: Session = SessionLocal()
        try:
            request = db.query(URLInjectionRequest).filter(
                URLInjectionRequest.request_id == request_id
            ).first()
            
            if request:
                request.mark_processed()
                db.commit()
                return True
            return False
        except Exception as e:
            db.rollback()
            print(f"Error marking request as processed: {e}")
            return False
        finally:
            db.close()
    
    def create_manual_request(self, url: str, email: str, admin_username: str) -> Optional[URLInjectionRequest]:
        """Create a URL injection request manually through admin panel (bypasses email confirmation)"""
        import uuid
        from datetime import datetime, timedelta
        
        db: Session = SessionLocal()
        try:
            # Check if a similar request already exists
            existing_request = db.query(URLInjectionRequest).filter(
                URLInjectionRequest.url == url,
                URLInjectionRequest.is_expired == False
            ).first()
            
            if existing_request and not existing_request.is_processed:
                return None  # Request already exists
            
            # Create new request
            new_request = URLInjectionRequest(
                request_id=str(uuid.uuid4()),
                url=url,
                requester_email=email,
                confirmation_token=str(uuid.uuid4()),
                created_at=datetime.utcnow(),
                expires_at=datetime.utcnow() + timedelta(days=7),  # 7 days expiry
                is_confirmed=True,  # Admin requests are automatically confirmed
                confirmed_at=datetime.utcnow(),
                is_processed=False,
                is_expired=False,
                admin_created=True,
                admin_username=admin_username
            )
            
            db.add(new_request)
            db.commit()
            
            # Refresh to get the actual database object
            db.refresh(new_request)
            
            return new_request
            
        except Exception as e:
            db.rollback()
            print(f"Error creating manual request: {e}")
            return None
        finally:
            db.close()

# Global instance
url_confirmation_service = URLConfirmationService()