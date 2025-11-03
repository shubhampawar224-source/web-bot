import base64
import io
import json
import os
import re
import secrets
import time
import uuid
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from flask import render_template_string, Flask, request
import loges
from utils.voice_bot_helper import refine_text_with_gpt, retrieve_faiss_response
from utils.query_senetizer import is_safe_query
from database.db import init_db
from utils.scraper import build_about
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, HttpUrl
from fastapi import FastAPI, WebSocket
from typing import Optional, List
from sqlalchemy.orm import Session
from database.db import SessionLocal
from model.models import Contact, Website, Firm
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from model.validation_schema import ChatRequest, ContactIn, SecurityHeadersMiddleware, URLPayload

# New models for URL injection with email confirmation
class URLInjectionRequest(BaseModel):
    url: HttpUrl
    email: str

class URLInjectionResponse(BaseModel):
    status: str
    message: str
    request_id: Optional[str] = None
from utils.voice_bot_helper import client
from voice_config.voice_helper import *
from utils.email_send import ContactManager
from utils.url_confirmation_service import url_confirmation_service
from utils.admin_auth_service import admin_auth_service
from utils.google_oauth_service import google_oauth_service


# from cache_manager import load_website_text
from utils.llm_tools import get_answer_from_db
from utils.vector_store import (
    collection,
    embedding_model,
    chunk_text,
    add_text_chunks_to_collection,
    query_similar_texts
)

load_dotenv()
ALLOWED_IFRAME_ORIGINS = os.getenv("ALLOWED_IFRAME_ORIGINS", "")  # space-separated list e.g. "https://siteA.com https://siteB.com"


# ---------------- Disable HuggingFace Tokenizer Warning ----------------
os.environ["TOKENIZERS_PARALLELISM"] = "false"
loges.log_check(message="INFO")
# ---------------- FastAPI setup ----------------
app = FastAPI()
contact_mgr = ContactManager()

@app.on_event("startup")
async def startup_event():
    """Initialize database tables and test connectivity on application startup"""
    try:
        print("🔧 Initializing database tables...")
        init_db()
        print("✅ Database tables initialized successfully!")
        
        # Test OpenAI API connectivity
        print("🔧 Testing OpenAI API connectivity...")
        from utils.llm_tools import test_connectivity
        if test_connectivity():
            print("✅ OpenAI API connectivity verified!")
        else:
            print("⚠️  OpenAI API connectivity test failed - chat functionality may be limited")
        
        # Initialize admin system
        print("🔧 Initializing admin system...")
        admin_auth_service.initialize_default_admin()
        print("✅ Admin system initialized!")
            
    except Exception as e:
        print(f"❌ Error during startup: {e}")
        # Don't raise exception to allow app to start, but log the error
        import traceback
        traceback.print_exc()

# After CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

@app.middleware("http")
async def allow_iframe(request, call_next):
    response = await call_next(request)

    # Allow embedding anywhere
    response.headers["Content-Security-Policy"] = "frame-ancestors *;"
    
    # Old browser fallback
    response.headers["X-Frame-Options"] = "ALLOWALL"
    
    # Allow widget JS to fetch API
    response.headers["Access-Control-Allow-Origin"] = "*"

    return response


# Add CSP + Security middleware
app.add_middleware(SecurityHeadersMiddleware)
app.mount("/static", StaticFiles(directory="static"), name="static")


voice_assistant = VoiceAssistant()
# ---------------- Helper ----------------
def get_session_history(session_id: str):
    results = collection.get(
        where={"session_id": session_id},
        include=["documents", "metadatas"]
    )
    history = []
    for doc, meta in zip(results["documents"], results["metadatas"]):
        if meta.get("role") in ["user", "assistant"]:
            history.append({"role": meta["role"], "content": doc})
    return history

# ----- APIs -----
@app.get("/", response_class=HTMLResponse)
async def index():
    return FileResponse("static/index.html")


@app.get("/voice")
async def get_index():
    return FileResponse("static/voice.html")


@app.post("/chat")
async def chat_endpoint(data: ChatRequest):
    session_id = data.session_id or str(uuid.uuid4())
    query = data.query
    firm_id = data.firm_id
    
    if not query or not firm_id:
        return JSONResponse({"error": "Query and firm are required"}, status_code=400)
    
    if not is_safe_query(query):
        raise HTTPException(status_code=400, detail="Not valid query detected. please ask anything else.")

    db: Session = SessionLocal()
    try:
        # Validate firm exists
        firm = db.query(Firm).filter(Firm.id == firm_id).first()
        if not firm:
            return JSONResponse({"error": "Selected firm not found"}, status_code=404)

        # Get firm-specific answer from vector DB
        answer = get_answer_from_db(query=query, session_id=session_id, firm_id=firm.id)
        if answer == "CONVERSATION_ENDED":
            answer = {
                "action": "SHOW_CONTACT_FORM",
                "message": "Before we finish, we would like to collect your contact details so our team can assist further."
            }
        return {"answer": answer, "session_id": session_id}

    finally:
        db.close()


@app.post("/inject-url")
async def inject_url(payload: URLPayload):
    """Direct URL injection without email confirmation"""
    db: Session = SessionLocal()
    try:
        url_str = str(payload.url)
        
        # Check if URL already exists
        existing_site = db.query(Website).filter(Website.base_url == url_str).first()
        if existing_site:
            firm_name = existing_site.firm.name if existing_site.firm else "Unknown"
            return {"status": "error", "message": f"This URL already exists in our database (Firm: {firm_name})"}

        # Process the URL using the scraper
        about_obj = await build_about(url_str)
        
        if not about_obj:
            return {"status": "error", "message": "Failed to scrape content from the URL"}

        full_text = about_obj.get("full_text", "").strip()
        if not full_text:
            return {"status": "error", "message": "No text content found on the webpage"}
            
        # Process and store the content
        chunks = chunk_text(full_text)
        metadata = {
            "type": "website",
            "url": url_str,
            "firm_name": about_obj.get("firm_name"),
            "session_id": payload.session_id or "global"
        }
        add_text_chunks_to_collection(chunks, metadata)

        return {
            "status": "success",
            "message": f"Successfully processed and added {len(chunks)} content chunks to knowledge base",
            "data": {
                "url": url_str,
                "firm_name": about_obj.get("firm_name"),
                "firm_id": about_obj.get("firm_id"),
                "indexed_chunks": len(chunks)
            }
        }

    except Exception as e:
        print(f"Error in inject_url: {e}")
        return {"status": "error", "message": f"Failed to process URL: {str(e)}"}
    finally:
        db.close()

@app.get("/firms")
async def get_all_firms():
    """
    Fetch all firms to populate a dropdown in the frontend.
    Cleans the firm name by removing 'www.' and '.com'.
    """
    db: Session = SessionLocal()
    try:
        firms = db.query(Firm).all()
        firm_list = []
        for firm in firms:
            clean_name = re.sub(r"^(www\.)|(\.com)$", "", firm.name, flags=re.IGNORECASE)
            firm_list.append({"id": firm.id, "name": clean_name})
        return {"status": "success", "firms": firm_list}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.post("/save-contact")
async def save_contact(payload: ContactIn, background_tasks: BackgroundTasks):
    try:
        # prefer explicit notify_to, otherwise send to the contact's email
        notify_to = payload.notify_to or payload.email
        contact_id = contact_mgr.save_and_notify(
            payload.model_dump(),
            background_tasks=background_tasks,
            notify_to=notify_to
        )
        return {"status": "ok", "id": contact_id}
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@app.get("/history/{session_id}")
async def get_history(session_id: str):
    """Fetch full chat history from vector DB"""
    return {"session_id": session_id, "history": get_session_history(session_id)}

@app.get("/widget")
async def get_widget():
    return FileResponse("static/widgets.html")
  
# ----------------- WebSocket voice assistant ----------------

@app.get("/chat_widget", response_class=HTMLResponse)
def chat_ui():
    with open("static/index.html") as f:
        return f.read()

@app.get("/config")
def get_config():
    return {
        "baseUrl": os.getenv("WIDGET_BASE_URL")  # only public value
    }

# ---------------- URL Injection with Email Confirmation ----------------

@app.post("/request-url-injection", response_model=URLInjectionResponse)
async def request_url_injection(payload: URLInjectionRequest):
    """
    Request URL injection with email confirmation.
    Creates a pending request and sends confirmation email.
    """
    try:
        url_str = str(payload.url)
        email = payload.email.strip().lower()
        
        # Validate email format
        import re
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email):
            return URLInjectionResponse(
                status="error",
                message="Invalid email format"
            )
        
        # Create request and send email
        request = url_confirmation_service.create_and_send_request(url_str, email)
        
        if request:
            return URLInjectionResponse(
                status="success",
                message=f"Confirmation email sent to {email}. Please check your inbox and click the confirmation link.",
                request_id=request.request_id
            )
        else:
            # Check if URL already exists or has pending request
            db: Session = SessionLocal()
            try:
                existing_site = db.query(Website).filter(Website.base_url == url_str).first()
                if existing_site:
                    return URLInjectionResponse(
                        status="error",
                        message="This URL is already in our database"
                    )
                else:
                    return URLInjectionResponse(
                        status="error", 
                        message="A pending confirmation request already exists for this URL or email sending failed"
                    )
            finally:
                db.close()
                
    except Exception as e:
        print(f"Error in request_url_injection: {e}")
        return URLInjectionResponse(
            status="error",
            message="An error occurred while processing your request"
        )

@app.get("/confirm-url-injection/{token}")
async def confirm_url_injection(token: str):
    """
    Confirm URL injection request using the email token.
    Processes the URL immediately upon confirmation.
    """
    try:
        success, message = url_confirmation_service.confirm_request(token)
        
        if success:
            # Process confirmed requests immediately
            background_tasks = BackgroundTasks()
            background_tasks.add_task(process_confirmed_urls)
            
            html_response = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>✅ URL Injection Confirmed</title>
                <style>
                    body {{ font-family: Arial, sans-serif; max-width: 600px; margin: 50px auto; padding: 20px; text-align: center; }}
                    .success {{ color: #27ae60; }}
                    .container {{ background-color: #f8f9fa; padding: 30px; border-radius: 10px; border: 2px solid #27ae60; }}
                    .processing {{ color: #3498db; margin-top: 20px; }}
                    .button {{ display: inline-block; background-color: #27ae60; color: white; padding: 10px 20px; 
                              text-decoration: none; border-radius: 5px; margin-top: 20px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1 class="success">✅ Confirmation Successful!</h1>
                    <p><strong>Your URL injection request has been confirmed and approved.</strong></p>
                    <div class="processing">
                        <p>🔄 The URL is now being processed and will be added to our assistant's knowledge base shortly.</p>
                        <p>You can now close this window and continue using the chat assistant.</p>
                    </div>
                    <a href="#" onclick="window.close()" class="button">Close Window</a>
                </div>
            </body>
            </html>
            """
            return HTMLResponse(content=html_response)
        else:
            error_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>❌ Confirmation Failed</title>
                <style>
                    body {{ font-family: Arial, sans-serif; max-width: 600px; margin: 50px auto; padding: 20px; text-align: center; }}
                    .error {{ color: #e74c3c; }}
                    .container {{ background-color: #f8f9fa; padding: 30px; border-radius: 10px; border: 2px solid #e74c3c; }}
                    .button {{ display: inline-block; background-color: #e74c3c; color: white; padding: 10px 20px; 
                              text-decoration: none; border-radius: 5px; margin-top: 20px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1 class="error">❌ Confirmation Failed</h1>
                    <p><strong>Error:</strong> {message}</p>
                    <p>Please try requesting the URL injection again or contact support if the problem persists.</p>
                    <a href="#" onclick="window.close()" class="button">Close Window</a>
                </div>
            </body>
            </html>
            """
            return HTMLResponse(content=error_html)
            
    except Exception as e:
        print(f"Error in confirm_url_injection: {e}")
        return HTMLResponse(content=f"""
        <!DOCTYPE html>
        <html>
        <head><title>❌ Error</title></head>
        <body style="font-family: Arial, sans-serif; text-align: center; margin: 50px;">
            <h1 style="color: #e74c3c;">❌ An Error Occurred</h1>
            <p>Please try again later or contact support.</p>
        </body>
        </html>
        """)

async def process_confirmed_urls():
    """Background task to process all confirmed URL requests"""
    try:
        confirmed_requests = url_confirmation_service.get_pending_confirmed_requests()
        
        for request in confirmed_requests:
            try:
                print(f"🔄 Processing confirmed URL: {request.url}")
                
                # Use existing scraper logic to add URL to database
                db: Session = SessionLocal()
                try:
                    result = build_about(request.url, db)
                    if result.get("status") == "success":
                        print(f"✅ Successfully processed URL: {request.url}")
                        url_confirmation_service.mark_request_processed(request.request_id)
                    else:
                        print(f"❌ Failed to process URL: {request.url} - {result.get('message', 'Unknown error')}")
                finally:
                    db.close()
                    
            except Exception as e:
                print(f"❌ Error processing URL {request.url}: {e}")
                
    except Exception as e:
        print(f"❌ Error in process_confirmed_urls: {e}")

@app.get("/pending-url-requests")
async def get_pending_requests():
    """Get all pending URL injection requests (for admin purposes)"""
    try:
        pending = url_confirmation_service.get_pending_confirmed_requests()
        return {
            "status": "success",
            "pending_requests": [
                {
                    "request_id": req.request_id,
                    "url": req.url,
                    "email": req.requester_email,
                    "created_at": req.created_at.isoformat(),
                    "confirmed_at": req.confirmed_at.isoformat() if req.confirmed_at else None
                }
                for req in pending
            ]
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ---------------- Admin Panel Endpoints ----------------

@app.get("/admin", response_class=HTMLResponse)
async def admin_panel():
    """Serve admin dashboard"""
    return FileResponse("static/admin.html")

# Admin Authentication Models
class AdminLoginRequest(BaseModel):
    username: str
    password: str

class AdminResponse(BaseModel):
    status: str
    message: str
    token: Optional[str] = None
    admin: Optional[dict] = None

@app.post("/admin/login", response_model=AdminResponse)
async def admin_login(payload: AdminLoginRequest):
    """Admin login endpoint"""
    try:
        success, token, admin_info = admin_auth_service.authenticate_admin(
            payload.username, payload.password
        )
        
        if success:
            return AdminResponse(
                status="success",
                message="Login successful",
                token=token,
                admin=admin_info
            )
        else:
            return AdminResponse(
                status="error",
                message="Invalid username or password"
            )
    except Exception as e:
        return AdminResponse(
            status="error",
            message="Login failed"
        )

@app.post("/admin/logout")
async def admin_logout(request: Request):
    """Admin logout endpoint"""
    try:
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            admin_auth_service.logout_admin(token)
        
        return {"status": "success", "message": "Logged out successfully"}
    except Exception as e:
        return {"status": "error", "message": "Logout failed"}

# Google OAuth endpoints
@app.get("/admin/oauth/google")
async def google_oauth_login():
    """Initiate Google OAuth login"""
    try:
        state = secrets.token_urlsafe(32)
        authorization_url = google_oauth_service.get_authorization_url(state)
        
        # Store state in a more secure way in production
        return {
            "status": "success",
            "authorization_url": authorization_url,
            "state": state
        }
    except Exception as e:
        return {"status": "error", "message": "Failed to initiate OAuth login"}

@app.get("/admin/oauth/callback")
async def google_oauth_callback(request: Request, code: str = None, state: str = None, error: str = None):
    """Handle Google OAuth callback"""
    try:
        if error:
            return HTMLResponse(f"""
            <!DOCTYPE html>
            <html>
            <head><title>Login Error</title></head>
            <body style="font-family: Arial; text-align: center; margin: 50px;">
                <h1 style="color: #e74c3c;">Authentication Error</h1>
                <p>Error: {error}</p>
                <p><a href="/admin">Return to Admin Login</a></p>
            </body>
            </html>
            """)
        
        if not code:
            return HTMLResponse("""
            <!DOCTYPE html>
            <html>
            <head><title>Login Error</title></head>
            <body style="font-family: Arial; text-align: center; margin: 50px;">
                <h1 style="color: #e74c3c;">Authentication Error</h1>
                <p>No authorization code received</p>
                <p><a href="/admin">Return to Admin Login</a></p>
            </body>
            </html>
            """)
        
        # Exchange code for token
        token_data = await google_oauth_service.exchange_code_for_token(code)
        if not token_data:
            return HTMLResponse("""
            <!DOCTYPE html>
            <html>
            <head><title>Login Error</title></head>
            <body style="font-family: Arial; text-align: center; margin: 50px;">
                <h1 style="color: #e74c3c;">Authentication Error</h1>
                <p>Failed to exchange code for token</p>
                <p><a href="/admin">Return to Admin Login</a></p>
            </body>
            </html>
            """)
        
        # Get user info from Google
        user_info = await google_oauth_service.get_user_info(token_data["access_token"])
        if not user_info:
            return HTMLResponse("""
            <!DOCTYPE html>
            <html>
            <head><title>Login Error</title></head>
            <body style="font-family: Arial; text-align: center; margin: 50px;">
                <h1 style="color: #e74c3c;">Authentication Error</h1>
                <p>Failed to get user information from Google</p>
                <p><a href="/admin">Return to Admin Login</a></p>
            </body>
            </html>
            """)
        
        # Create or update admin user
        success, admin_user, message = google_oauth_service.create_or_update_admin_user(user_info)
        if not success:
            return HTMLResponse(f"""
            <!DOCTYPE html>
            <html>
            <head><title>Access Denied</title></head>
            <body style="font-family: Arial; text-align: center; margin: 50px;">
                <h1 style="color: #e74c3c;">Access Denied</h1>
                <p>{message}</p>
                <p><a href="/admin">Return to Admin Login</a></p>
            </body>
            </html>
            """)
        
        # Create admin session
        session_token = google_oauth_service.create_admin_session(admin_user)
        if not session_token:
            return HTMLResponse("""
            <!DOCTYPE html>
            <html>
            <head><title>Login Error</title></head>
            <body style="font-family: Arial; text-align: center; margin: 50px;">
                <h1 style="color: #e74c3c;">Session Error</h1>
                <p>Failed to create admin session</p>
                <p><a href="/admin">Return to Admin Login</a></p>
            </body>
            </html>
            """)
        
        # Get admin info
        admin_info = google_oauth_service.get_admin_info_dict(admin_user)
        
        # Prepare JSON string for JavaScript (escape single quotes)
        admin_info_json = json.dumps(admin_info).replace("'", "\\'")
        
        # Return success page with auto-redirect to admin dashboard
        return HTMLResponse(f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Login Successful</title>
            <style>
                body {{ font-family: Arial, sans-serif; text-align: center; margin: 50px; }}
                .success {{ color: #27ae60; }}
                .container {{ max-width: 500px; margin: 0 auto; padding: 30px; background: #f8f9fa; border-radius: 10px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1 class="success">✅ Login Successful!</h1>
                <p>Welcome, {admin_user.full_name}!</p>
                <p>Redirecting to admin dashboard...</p>
                <p><a href="/admin">Click here if not redirected automatically</a></p>
            </div>
            
            <script>
                // Store auth data and redirect
                localStorage.setItem('admin_token', '{session_token}');
                localStorage.setItem('admin_info', '{admin_info_json}');
                
                setTimeout(() => {{
                    window.location.href = '/admin';
                }}, 2000);
            </script>
        </body>
        </html>
        """)
        
    except Exception as e:
        print(f"OAuth callback error: {e}")
        return HTMLResponse(f"""
        <!DOCTYPE html>
        <html>
        <head><title>Login Error</title></head>
        <body style="font-family: Arial; text-align: center; margin: 50px;">
            <h1 style="color: #e74c3c;">Authentication Error</h1>
            <p>An unexpected error occurred during authentication</p>
            <p><a href="/admin">Return to Admin Login</a></p>
        </body>
        </html>
        """)

# Admin middleware for authentication
async def verify_admin_auth(request: Request):
    """Verify admin authentication"""
    auth_header = request.headers.get("authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="No valid authentication token")
    
    token = auth_header.split(" ")[1]
    valid, admin_info = admin_auth_service.validate_session(token)
    
    if not valid:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    return admin_info

@app.get("/admin/stats")
async def get_admin_stats(request: Request):
    """Get dashboard statistics"""
    admin_info = await verify_admin_auth(request)
    
    db: Session = SessionLocal()
    try:
        from model.url_injection_models import URLInjectionRequest
        from datetime import datetime
        
        # Count total websites (direct injections)
        total_websites = db.query(Website).count()
        
        # Count URL injection requests
        total_url_requests = db.query(URLInjectionRequest).count()
        
        # Count pending URLs (confirmed but not processed)
        pending_urls = db.query(URLInjectionRequest).filter(
            URLInjectionRequest.is_confirmed == True,
            URLInjectionRequest.is_processed == False
        ).count()
        
        # Count processed URLs from email system
        processed_email_urls = db.query(URLInjectionRequest).filter(
            URLInjectionRequest.is_processed == True
        ).count()
        
        # Total processed URLs = websites + processed email requests
        total_processed_urls = total_websites + processed_email_urls
        
        total_contacts = db.query(Contact).count()
        total_firms = db.query(Firm).count()
        
        return {
            "status": "success",
            "stats": {
                "total_urls": total_processed_urls,  # All processed URLs
                "pending_urls": pending_urls,        # Waiting to be processed
                "direct_urls": total_websites,       # Direct injections
                "email_requests": total_url_requests, # Total email requests
                "total_contacts": total_contacts,
                "total_firms": total_firms
            }
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        db.close()

@app.get("/admin/url-requests")
async def get_url_requests(request: Request, status: str = "all"):
    """Get URL injection requests"""
    admin_info = await verify_admin_auth(request)
    
    db: Session = SessionLocal()
    try:
        from model.url_injection_models import URLInjectionRequest
        
        query = db.query(URLInjectionRequest)
        
        if status == "pending":
            query = query.filter(URLInjectionRequest.is_confirmed == False)
        elif status == "confirmed":
            query = query.filter(
                URLInjectionRequest.is_confirmed == True,
                URLInjectionRequest.is_processed == False
            )
        elif status == "processed":
            query = query.filter(URLInjectionRequest.is_processed == True)
        elif status == "expired":
            from datetime import datetime
            query = query.filter(URLInjectionRequest.expires_at < datetime.now())
        
        requests = query.order_by(URLInjectionRequest.created_at.desc()).all()
        
        return {
            "status": "success",
            "requests": [
                {
                    "id": req.id,
                    "request_id": req.request_id,
                    "url": req.url,
                    "requester_email": req.requester_email,
                    "is_confirmed": req.is_confirmed,
                    "is_processed": req.is_processed,
                    "created_at": req.created_at.isoformat(),
                    "confirmed_at": req.confirmed_at.isoformat() if req.confirmed_at else None,
                    "processed_at": req.processed_at.isoformat() if req.processed_at else None,
                    "is_expired": req.is_expired(),
                    "source": "email_request"
                }
                for req in requests
            ]
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        db.close()

@app.get("/admin/all-urls")
async def get_all_urls(request: Request):
    """Get all injected URLs from both email requests and direct injections"""
    admin_info = await verify_admin_auth(request)
    
    db: Session = SessionLocal()
    try:
        from model.url_injection_models import URLInjectionRequest
        from datetime import datetime
        
        all_urls = []
        
        # Get URL injection requests (email confirmation system)
        url_requests = db.query(URLInjectionRequest).order_by(URLInjectionRequest.created_at.desc()).all()
        
        for req in url_requests:
            all_urls.append({
                "id": f"req_{req.id}",
                "request_id": req.request_id,
                "url": req.url,
                "requester_email": req.requester_email,
                "is_confirmed": req.is_confirmed,
                "is_processed": req.is_processed,
                "created_at": req.created_at.isoformat(),
                "confirmed_at": req.confirmed_at.isoformat() if req.confirmed_at else None,
                "processed_at": req.processed_at.isoformat() if req.processed_at else None,
                "is_expired": req.is_expired(),
                "source": "email_request",
                "status_text": "Expired" if req.is_expired() else ("Processed" if req.is_processed else ("Confirmed" if req.is_confirmed else "Pending"))
            })
        
        # Get directly injected websites
        websites = db.query(Website).order_by(Website.created_at.desc()).all()
        
        for website in websites:
            # Check if this URL is already in the requests (to avoid duplicates)
            existing_request = any(url['url'] == website.base_url for url in all_urls)
            
            if not existing_request:
                all_urls.append({
                    "id": f"web_{website.id}",
                    "request_id": f"direct_{website.id}",
                    "url": website.base_url,
                    "requester_email": "Direct Injection",
                    "is_confirmed": True,
                    "is_processed": True,
                    "created_at": website.created_at.isoformat(),
                    "confirmed_at": website.created_at.isoformat(),
                    "processed_at": website.created_at.isoformat(),
                    "is_expired": False,
                    "source": "direct_injection",
                    "status_text": "Processed",
                    "firm_name": website.firm.name if website.firm else "Unknown"
                })
        
        # Sort all URLs by creation date (newest first)
        all_urls.sort(key=lambda x: x['created_at'], reverse=True)
        
        return {
            "status": "success",
            "requests": all_urls
        }
        
    except Exception as e:
        print(f"Error in get_all_urls: {e}")
        return {"status": "error", "message": str(e)}

@app.post("/admin/process-url/{request_id}")
async def admin_process_url(request_id: str, request: Request):
    """Manually process a confirmed URL request"""
    admin_info = await verify_admin_auth(request)
    
    try:
        # Process the URL using existing logic
        db: Session = SessionLocal()
        from model.url_injection_models import URLInjectionRequest
        
        url_request = db.query(URLInjectionRequest).filter(
            URLInjectionRequest.request_id == request_id
        ).first()
        
        if not url_request or not url_request.is_confirmed:
            return {"status": "error", "message": "Request not found or not confirmed"}
        
        if url_request.is_processed:
            return {"status": "error", "message": "Request already processed"}
        
        # Process URL using existing scraper
        result = build_about(url_request.url, db)
        
        if result.get("status") == "success":
            url_confirmation_service.mark_request_processed(request_id)
            return {"status": "success", "message": "URL processed successfully"}
        else:
            return {"status": "error", "message": result.get("message", "Processing failed")}
            
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        db.close()

@app.get("/admin/contacts")
async def get_admin_contacts(request: Request):
    """Get all contacts for admin"""
    admin_info = await verify_admin_auth(request)
    
    db: Session = SessionLocal()
    try:
        contacts = db.query(Contact).order_by(Contact.created_at.desc()).all()
        
        return {
            "status": "success",
            "contacts": [
                {
                    "id": contact.id,
                    "fname": contact.fname,
                    "lname": contact.lname,
                    "email": contact.email,
                    "phone_number": contact.phone_number,
                    "created_at": contact.created_at.isoformat()
                }
                for contact in contacts
            ]
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        db.close()

@app.get("/admin/firms")
async def get_admin_firms(request: Request):
    """Get all firms for admin"""
    admin_info = await verify_admin_auth(request)
    
    db: Session = SessionLocal()
    try:
        firms = db.query(Firm).order_by(Firm.created_at.desc()).all()
        
        return {
            "status": "success",
            "firms": [
                {
                    "id": firm.id,
                    "name": firm.name,
                    "created_at": firm.created_at.isoformat(),
                    "website_count": len(firm.websites) if hasattr(firm, 'websites') else 0
                }
                for firm in firms
            ]
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        db.close()

@app.delete("/admin/contact/{contact_id}")
async def delete_contact(contact_id: int, request: Request):
    """Delete a contact"""
    admin_info = await verify_admin_auth(request)
    
    db: Session = SessionLocal()
    try:
        contact = db.query(Contact).filter(Contact.id == contact_id).first()
        if not contact:
            return {"status": "error", "message": "Contact not found"}
        
        db.delete(contact)
        db.commit()
        
        return {"status": "success", "message": "Contact deleted successfully"}
    except Exception as e:
        db.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        db.close()

@app.post("/admin/bulk-process-urls")
async def bulk_process_urls(request: Request):
    """Process all confirmed URLs"""
    admin_info = await verify_admin_auth(request)
    
    try:
        # Use a direct database query to avoid schema issues
        db: Session = SessionLocal()
        try:
            from model.url_injection_models import URLInjectionRequest
            
            # Get confirmed but unprocessed requests directly with basic fields
            confirmed_requests = db.query(URLInjectionRequest).filter(
                URLInjectionRequest.is_confirmed == True,
                URLInjectionRequest.is_processed == False
            ).all()
            
        except Exception as db_error:
            # Fallback if there are schema issues - create a minimal query
            print(f"Database schema issue: {db_error}")
            db.close()
            return {
                "status": "error", 
                "message": "Database schema issue. Please check if the url_injection_requests table has all required columns."
            }
        finally:
            db.close()
            
        processed_count = 0
        failed_count = 0
        
        for url_request in confirmed_requests:
            try:
                db: Session = SessionLocal()
                try:
                    # Use the async build_about function correctly
                    result = await build_about(url_request.url)
                    
                    if result and result.get("full_text"):
                        # Process the content like the direct injection
                        full_text = result.get("full_text", "").strip()
                        if full_text:
                            chunks = chunk_text(full_text)
                            metadata = {
                                "type": "website",
                                "url": url_request.url,
                                "firm_name": result.get("firm_name"),
                                "session_id": "email_confirmed"
                            }
                            add_text_chunks_to_collection(chunks, metadata)
                            
                            # Mark as processed
                            url_request.is_processed = True
                            url_request.processed_at = datetime.utcnow()
                            if hasattr(url_request, 'processed_by'):
                                url_request.processed_by = admin_info.get('username', 'admin')
                            db.commit()
                            
                            processed_count += 1
                        else:
                            failed_count += 1
                            print(f"No content found for URL: {url_request.url}")
                    else:
                        failed_count += 1
                        print(f"Failed to scrape URL: {url_request.url}")
                        
                except Exception as process_error:
                    failed_count += 1
                    print(f"Failed to process URL {url_request.url}: {process_error}")
                    db.rollback()
                finally:
                    db.close()
                    
            except Exception as e:
                failed_count += 1
                print(f"Failed to process URL {url_request.url}: {e}")
        
        return {
            "status": "success",
            "message": f"Processed {processed_count} URLs, {failed_count} failed",
            "processed": processed_count,
            "failed": failed_count
        }
    except Exception as e:
        print(f"Bulk process error: {e}")
        return {"status": "error", "message": f"Bulk processing failed: {str(e)}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# Manual URL Injection Models
class ManualURLInjectionRequest(BaseModel):
    url: str
    email: str

@app.post("/admin/manual-url-injection")
async def manual_url_injection(payload: ManualURLInjectionRequest, request: Request):
    """Manually inject URL directly through admin panel"""
    admin_info = await verify_admin_auth(request)
    
    try:
        url_str = str(payload.url).strip()
        email = payload.email.strip() or 'admin@system.local'
        
        # Validate URL format
        if not url_str.startswith(('http://', 'https://')):
            return {"status": "error", "message": "URL must start with http:// or https://"}
        
        # Check if URL already exists in database
        db: Session = SessionLocal()
        try:
            existing_site = db.query(Website).filter(Website.base_url == url_str).first()
            if existing_site:
                return {"status": "error", "message": "This URL is already in our database"}
            
            # Create a URL injection request and mark it as confirmed and processed immediately
            request_obj = url_confirmation_service.create_manual_request(url_str, email, admin_info['username'])
            
            if request_obj:
                # Process the URL immediately
                result = build_about(url_str, db)
                
                if result.get("status") == "success":
                    # Mark the request as processed
                    url_confirmation_service.mark_request_processed(request_obj.request_id)
                    
                    return {
                        "status": "success",
                        "message": f"URL successfully injected and processed: {url_str}",
                        "request_id": request_obj.request_id
                    }
                else:
                    return {
                        "status": "error",
                        "message": f"URL injection failed: {result.get('message', 'Unknown error')}"
                    }
            else:
                return {"status": "error", "message": "Failed to create URL injection request"}
                
        finally:
            db.close()
            
    except Exception as e:
        print(f"Error in manual_url_injection: {e}")
        return {"status": "error", "message": "An error occurred while processing the URL injection"}

@app.post("/admin/inject-url")
async def admin_inject_url(payload: URLPayload, request: Request):
    """Admin URL injection endpoint - directly inject and process URLs"""
    admin_info = await verify_admin_auth(request)
    
    try:
        url_str = str(payload.url)
        
        # Validate URL format
        if not url_str.startswith(('http://', 'https://')):
            return {"status": "error", "message": "URL must start with http:// or https://"}
        
        db: Session = SessionLocal()
        try:
            # Check if URL already exists
            existing_site = db.query(Website).filter(Website.base_url == url_str).first()
            if existing_site:
                firm_name = existing_site.firm.name if existing_site.firm else "Unknown"
                return {"status": "error", "message": f"This URL already exists in our database (Firm: {firm_name})"}

            # Process the URL using the scraper
            about_obj = await build_about(url_str)
            
            if not about_obj:
                return {"status": "error", "message": "Failed to scrape content from the URL. Please check if the website is accessible."}

            full_text = about_obj.get("full_text", "").strip()
            if not full_text:
                return {"status": "error", "message": "No text content found on the webpage to add to knowledge base."}
                
            # Process and store the content
            chunks = chunk_text(full_text)
            metadata = {
                "type": "website",
                "url": url_str,
                "firm_name": about_obj.get("firm_name"),
                "session_id": "admin_injected",
                "injected_by": admin_info.get('username', 'admin')
            }
            add_text_chunks_to_collection(chunks, metadata)

            return {
                "status": "success",
                "message": f"Successfully processed and added {len(chunks)} content chunks to knowledge base",
                "data": {
                    "url": url_str,
                    "firm_name": about_obj.get("firm_name"),
                    "indexed_chunks": len(chunks),
                    "injected_by": admin_info.get('username', 'admin')
                }
            }
            
        finally:
            db.close()
            
    except Exception as e:
        print(f"Error in admin_inject_url: {e}")
        return {"status": "error", "message": f"Failed to process URL: {str(e)}"}

@app.middleware("http")
async def frame_headers_middleware(request: Request, call_next):
    resp = await call_next(request)

    # remove restrictive headers if present (MutableHeaders: delete instead of pop)
    for hdr in ("Content-Security-Policy", "X-Frame-Options", "Permissions-Policy"):
        if hdr in resp.headers:
            try:
                del resp.headers[hdr]
            except Exception:
                pass

    if ALLOWED_IFRAME_ORIGINS:
        origins = ALLOWED_IFRAME_ORIGINS.split()
        allowed = " ".join(origins)
        resp.headers["Content-Security-Policy"] = f"frame-ancestors 'self' {allowed};"
        # do NOT re-add Permissions-Policy that blocks unload; only add explicit safe feature policies if you understand them
    else:
        resp.headers["Content-Security-Policy"] = "frame-ancestors *;"

    return resp

