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
from model.validation_schema import *
from voice_config.voice_helper import *
from utils.email_send import ContactManager
from utils.url_confirmation_service import url_confirmation_service
from utils.admin_auth_service import admin_auth_service
from utils.user_auth_service import user_auth_service
from utils.url_processing_service import url_processing_service


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


@app.post("/chat/deeplearning")
async def chat_deeplearning(data: dict):
    """Simple API for https://learn.deeplearning.ai/ URL - directly calls chat with firm context"""
    query = data.get("query")
    url = data.get("url", "")
    session_id = data.get("session_id") or str(uuid.uuid4())
    
    if not query:
        return JSONResponse({"error": "Query is required"}, status_code=400)
    
    if not is_safe_query(query):
        raise HTTPException(status_code=400, detail="Not valid query detected. please ask anything else.")
    
    # Check if URL matches the target URL
    if "learn.deeplearning.ai" in url:
        print(f"🎯 DeepLearning.ai chat: query='{query}', url='{url}'")
        
        db: Session = SessionLocal()
        try:
            # Find the firm for deeplearning.ai
            firm = db.query(Firm).filter(Firm.name.ilike('%deeplearning%')).first()
            
            if firm:
                print(f"✅ Found DeepLearning.ai firm: {firm.name} (ID: {firm.id})")
                # Use the existing chat logic with firm context
                answer = get_answer_from_db(query=query, session_id=session_id, firm_id=firm.id)
            else:
                print("⚠️ DeepLearning.ai firm not found, using general knowledge")
                answer = get_answer_from_db(query=query, session_id=session_id)
            
            if answer == "CONVERSATION_ENDED":
                answer = {
                    "action": "SHOW_CONTACT_FORM",
                    "message": "Before we finish, we would like to collect your contact details so our team can assist further."
                }
            
            return {"answer": answer, "session_id": session_id, "url": url}
            
        finally:
            db.close()
    else:
        return JSONResponse({"error": "This endpoint is only for learn.deeplearning.ai URLs"}, status_code=400)


@app.post("/chat/url-specific")
async def chat_url_specific(data: dict):
    """Chat endpoint for URL-specific conversations launched from user dashboard"""
    session_id = data.get("session_id") or str(uuid.uuid4())
    query = data.get("query")
    url_ids = data.get("url_ids")  # Comma-separated URL IDs
    user_id = data.get("user_id")
    firm_id = data.get("firm_id")  # Direct firm_id parameter
    
    print(f"🗨️ URL-specific chat: query='{query}', url_ids={url_ids}, user_id={user_id}, firm_id={firm_id}")
    
    if not query:
        return JSONResponse({"error": "Query is required"}, status_code=400)
    
    if not is_safe_query(query):
        raise HTTPException(status_code=400, detail="Not valid query detected. please ask anything else.")

    db: Session = SessionLocal()
    try:
        request_ids = []
        
        # If firm_id is provided directly, use it
        if firm_id:
            print(f"🏢 Using provided firm_id: {firm_id}")
            firm = db.query(Firm).filter(Firm.id == firm_id).first()
            if firm:
                print(f"✅ Found firm: {firm.name}")
            else:
                print(f"❌ Firm with ID {firm_id} not found")
                
        # If URL IDs provided, get request_ids and firm from URLs (if firm_id not already set)
        elif url_ids:
            from model.url_injection_models import URLInjectionRequest
            url_id_list = [int(id.strip()) for id in url_ids.split(',') if id.strip().isdigit()]
            print(f"📝 Parsed URL IDs: {url_id_list}")
            
            if url_id_list:
                url_requests = db.query(URLInjectionRequest).filter(
                    URLInjectionRequest.id.in_(url_id_list),
                    URLInjectionRequest.status == "completed"
                ).all()
                
                print(f"🔎 Found {len(url_requests)} completed URL requests")
                
                if url_requests:
                    # Get request IDs for vector search
                    request_ids = [url_req.request_id for url_req in url_requests]
                    print(f"🔗 Request IDs for vector search: {request_ids}")
                    
                    # Get firm from first URL
                    first_url = url_requests[0]
                    if first_url.firm_id:
                        firm_id = first_url.firm_id
                        firm = db.query(Firm).filter(Firm.id == firm_id).first()
                        print(f"🏢 Using firm: {firm.name if firm else 'Unknown'} (ID: {firm_id})")

        # Use URL-specific context with request_ids
        if request_ids:
            print(f"🎯 Using URL-specific context with {len(request_ids)} request IDs")
            answer = get_answer_from_db(query=query, session_id=session_id, url_context=','.join(request_ids))
        elif firm_id:
            print(f"🏢 Fallback to firm-based search (firm_id: {firm_id})")
            answer = get_answer_from_db(query=query, session_id=session_id, firm_id=firm_id)
        else:
            print(f"🌐 Using general knowledge fallback")
            answer = get_answer_from_db(query=query, session_id=session_id)
            
        if answer == "CONVERSATION_ENDED":
            answer = {
                "action": "SHOW_CONTACT_FORM",
                "message": "Before we finish, we would like to collect your contact details so our team can assist further."
            }
        
        print(f"✅ Generated answer: {answer[:100] if isinstance(answer, str) else str(answer)[:100]}...")
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
async def get_widget(urls: Optional[str] = None, user_id: Optional[int] = None, firm_id: Optional[int] = None):
    """Serve widget with optional URL filtering and firm information"""
    return FileResponse("static/widgets.html")

@app.get("/widget/firm-info")
async def get_widget_firm_info(urls: Optional[str] = None, user_id: Optional[int] = None):
    """Get firm information for widget based on URL IDs"""
    try:
        print(f"🔍 Widget firm-info request: urls={urls}, user_id={user_id}")
        
        db: Session = SessionLocal()
        try:
            if urls:
                # Parse comma-separated URL IDs
                url_id_list = [int(id.strip()) for id in urls.split(',') if id.strip().isdigit()]
                print(f"📝 Parsed URL IDs: {url_id_list}")
                
                if url_id_list:
                    from model.url_injection_models import URLInjectionRequest
                    
                    # Get the first URL's firm (assuming all URLs from same user would have same firm context)
                    url_request = db.query(URLInjectionRequest).filter(
                        URLInjectionRequest.id.in_(url_id_list),
                        URLInjectionRequest.status == "completed"
                    ).first()
                    
                    print(f"🔎 Found URL request: {url_request.url if url_request else 'None'}")
                    print(f"🏢 Firm ID: {url_request.firm_id if url_request else 'None'}")
                    
                    if url_request and url_request.firm_id:
                        firm = db.query(Firm).filter(Firm.id == url_request.firm_id).first()
                        if firm:
                            print(f"✅ Firm found: {firm.name}")
                            return {
                                "status": "success",
                                "firm_id": firm.id,
                                "firm_name": firm.name
                            }
                        else:
                            print(f"❌ Firm with ID {url_request.firm_id} not found")
                    else:
                        print(f"⚠️ URL request has no firm_id or not found")
                        
                        # If no firm_id, try to assign one based on URL domain
                        if url_request:
                            from utils.url_processing_service import URLProcessingService
                            url_service = URLProcessingService()
                            firm_id = url_service.get_firm_from_url(url_request.url, db)
                            
                            if firm_id:
                                url_request.firm_id = firm_id
                                db.commit()
                                
                                firm = db.query(Firm).filter(Firm.id == firm_id).first()
                                print(f"� Auto-assigned firm: {firm.name if firm else 'Unknown'}")
                                return {
                                    "status": "success", 
                                    "firm_id": firm.id,
                                    "firm_name": firm.name
                                }
            
            print(f"�📤 Returning no firm info")
            return {
                "status": "success",
                "firm_id": None,
                "firm_name": None
            }
        finally:
            db.close()
    except Exception as e:
        print(f"❌ Widget firm-info error: {e}")
        return {
            "status": "error",
            "message": str(e)
        }


@app.get("/debug/vector-search")
async def debug_vector_search(request_id: str):
    """Debug endpoint to test vector search"""
    try:
        from utils.vector_store import collection
        from sentence_transformers import SentenceTransformer
        
        embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
        query_embedding = embedding_model.encode("test query").tolist()
        
        # Search for specific request_id
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=5,
            where={"request_id": request_id}
        )
        
        return {
            "status": "success",
            "found_documents": len(results["documents"][0]) if results["documents"] else 0,
            "metadata": results["metadatas"][0] if results["metadatas"] else [],
            "request_id_searched": request_id
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
  
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

# ---------------- Admin Panel Endpoints ----------------

@app.get("/admin", response_class=HTMLResponse)
async def admin_panel():
    """Serve admin dashboard"""
    return FileResponse("static/admin.html")

@app.get("/admin/signup", response_class=HTMLResponse)
async def admin_signup_page():
    """Serve admin signup page"""
    return FileResponse("static/admin-signup.html")

@app.get("/signup", response_class=HTMLResponse)
async def user_signup_page():
    """Serve user signup page"""
    return FileResponse("static/signup.html")

@app.get("/login", response_class=HTMLResponse)
async def user_login_page():
    """Serve user login page"""
    return FileResponse("static/login.html")

@app.get("/login.html", response_class=HTMLResponse)
async def user_login_page_redirect():
    """Redirect /login.html to /login for backward compatibility"""
    return FileResponse("static/login.html")

@app.get("/dashboard", response_class=HTMLResponse)
async def user_dashboard():
    """Serve user dashboard"""
    return FileResponse("static/user_dashboard.html")


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

@app.post("/admin/signup", response_model=AdminResponse)
async def admin_signup(payload: AdminSignupRequest):
    """Admin signup endpoint"""
    try:
        # Validate required fields
        if not payload.username or not payload.email or not payload.password:
            return AdminResponse(
                status="error",
                message="Username, email, and password are required"
            )
        
        # Check password strength (basic validation)
        if len(payload.password) < 6:
            return AdminResponse(
                status="error",
                message="Password must be at least 6 characters long"
            )
        
        # Create admin user
        success, message = admin_auth_service.create_admin_user(
            username=payload.username,
            email=payload.email,
            password=payload.password,
            full_name=payload.full_name,
            is_super_admin=payload.is_super_admin
        )
        
        if success:
            return AdminResponse(
                status="success",
                message=message
            )
        else:
            return AdminResponse(
                status="error",
                message=message
            )
    except Exception as e:
        print(f"❌ Admin signup error: {e}")
        return AdminResponse(
            status="error",
            message="Signup failed"
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

# User Authentication Endpoints
@app.post("/signup", response_model=UserResponse)
async def user_signup(payload: UserSignupRequest, request: Request):
    """User registration endpoint"""
    try:
        # Get client IP and user agent for session tracking
        client_ip = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent", "Unknown")
        
        success, message, user_info = user_auth_service.register_user(
            first_name=payload.first_name,
            last_name=payload.last_name,
            email=payload.email,
            password=payload.password,
            phone=payload.phone
        )
        
        if success:
            # Auto-login after successful registration
            login_success, token, login_user_info = user_auth_service.authenticate_user(
                email=payload.email,
                password=payload.password,
                device_info=user_agent,
                ip_address=client_ip
            )
            
            if login_success:
                return UserResponse(
                    status="success",
                    message="Registration successful. You are now logged in.",
                    token=token,
                    user=login_user_info
                )
            else:
                return UserResponse(
                    status="success",
                    message="Registration successful. Please log in.",
                    user=user_info
                )
        else:
            return UserResponse(
                status="error",
                message=message
            )
            
    except Exception as e:
        print(f"❌ Signup error: {e}")
        return UserResponse(
            status="error",
            message="Registration failed. Please try again."
        )

@app.post("/login", response_model=UserResponse)
async def user_login(payload: UserLoginRequest, request: Request):
    """User login endpoint"""
    try:
        # Get client IP and user agent for session tracking
        client_ip = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent", "Unknown")
        
        success, token, user_info = user_auth_service.authenticate_user(
            email=payload.email,
            password=payload.password,
            device_info=user_agent,
            ip_address=client_ip
        )
        
        if success:
            return UserResponse(
                status="success",
                message="Login successful",
                token=token,
                user=user_info
            )
        else:
            return UserResponse(
                status="error",
                message="Invalid email or password"
            )
            
    except Exception as e:
        print(f"❌ Login error: {e}")
        return UserResponse(
            status="error",
            message="Login failed. Please try again."
        )

@app.post("/logout")
async def user_logout(request: Request):
    """User logout endpoint"""
    try:
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            user_auth_service.logout_user(token)
        
        return {"status": "success", "message": "Logged out successfully"}
    except Exception as e:
        return {"status": "error", "message": "Logout failed"}

# User middleware for authentication
async def verify_user_auth(request: Request):
    """Verify user authentication"""
    auth_header = request.headers.get("authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="No valid authentication token")
    
    token = auth_header.split(" ")[1]
    valid, user_info = user_auth_service.validate_session(token)
    
    if not valid:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    return user_info

@app.get("/profile")
async def get_user_profile(request: Request):
    """Get current user profile"""
    try:
        user_info = await verify_user_auth(request)
        return {
            "status": "success",
            "user": user_info
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"❌ Profile error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get profile")

@app.put("/profile")
async def update_user_profile(request: Request, first_name: str = None, last_name: str = None, phone: str = None):
    """Update user profile"""
    try:
        user_info = await verify_user_auth(request)
        
        success, message = user_auth_service.update_user_profile(
            user_id=user_info["id"],
            first_name=first_name,
            last_name=last_name,
            phone=phone
        )
        
        if success:
            # Get updated user info
            updated_user = user_auth_service.get_user_by_id(user_info["id"])
            return {
                "status": "success",
                "message": message,
                "user": updated_user
            }
        else:
            return {
                "status": "error",
                "message": message
            }
            
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"❌ Profile update error: {e}")
        return {
            "status": "error",
            "message": "Failed to update profile"
        }

# User URL Management Endpoints
@app.get("/user/urls", response_model=UserUrlResponse)
async def get_user_urls(request: Request):
    """Get user's submitted URLs"""
    try:
        user_info = await verify_user_auth(request)
        
        db: Session = SessionLocal()
        try:
            from model.url_injection_models import URLInjectionRequest
            
            # Try to query URLs, but handle the case where user_id column might not exist yet
            try:
                urls = db.query(URLInjectionRequest).filter(
                    URLInjectionRequest.user_id == user_info["id"]
                ).order_by(URLInjectionRequest.created_at.desc()).all()
            except Exception as e:
                # If user_id column doesn't exist, return empty list for now
                print(f"⚠️ Could not query user URLs (likely missing user_id column): {e}")
                urls = []
            
            url_data = []
            for url in urls:
                url_data.append({
                    "id": url.id,
                    "url": url.url,
                    "description": getattr(url, 'description', ''),
                    "status": getattr(url, 'status', 'pending'),
                    "created_at": url.created_at.isoformat(),
                    "processed_at": url.processed_at.isoformat() if url.processed_at else None
                })
            
            return UserUrlResponse(
                status="success",
                message="URLs retrieved successfully",
                urls=url_data
            )
        finally:
            db.close()
            
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"❌ Get user URLs error: {e}")
        return UserUrlResponse(
            status="error",
            message="Failed to retrieve URLs"
        )

@app.post("/user/submit-url", response_model=UserUrlResponse)
async def submit_user_url(request: Request, payload: UserUrlRequest):
    """Submit and immediately process a new URL for user's chatbot"""
    try:
        user_info = await verify_user_auth(request)
        
        db: Session = SessionLocal()
        try:
            from model.url_injection_models import URLInjectionRequest
            from model.models import Website
            
            # Check if URL already exists
            existing_site = db.query(Website).filter(Website.base_url == payload.url).first()
            if existing_site:
                firm_name = existing_site.firm.name if existing_site.firm else "Unknown"
                return UserUrlResponse(
                    status="error",
                    message=f"This URL already exists in our database (Firm: {firm_name})"
                )
            
            # Try to create new URL request with user_id, fallback to basic request if column doesn't exist
            try:
                new_url_request = URLInjectionRequest.create_user_request(
                    url=payload.url,
                    user_id=user_info["id"],
                    email=user_info["email"],
                    description=payload.description or ""
                )
                # Set status to approved and processing
                new_url_request.status = "approved"
                new_url_request.processing_status = "processing"
            except Exception as e:
                print(f"⚠️ Could not create user request (likely missing user_id column): {e}")
                # Fallback to basic request creation
                new_url_request = URLInjectionRequest.create_request(
                    url=payload.url,
                    email=user_info["email"],
                    notes=payload.description or ""
                )
                new_url_request.is_confirmed = True
                new_url_request.processing_status = "processing"
            
            db.add(new_url_request)
            db.commit()
            db.refresh(new_url_request)
            
            # Process the URL immediately (scrape and add to vector store)
            try:
                # Scrape the URL
                about_obj = await build_about(payload.url)
                
                if not about_obj:
                    new_url_request.processing_status = "failed"
                    if hasattr(new_url_request, 'status'):
                        new_url_request.status = "failed"
                    new_url_request.notes = "Failed to scrape content from URL"
                    db.commit()
                    return UserUrlResponse(
                        status="error",
                        message="Failed to scrape content from URL"
                    )
                
                full_text = about_obj.get("full_text", "").strip()
                if not full_text:
                    new_url_request.processing_status = "failed"
                    if hasattr(new_url_request, 'status'):
                        new_url_request.status = "failed"
                    new_url_request.notes = "No text content found on webpage"
                    db.commit()
                    return UserUrlResponse(
                        status="error",
                        message="No text content found on webpage"
                    )
                
                # Process and store in vector database
                chunks = chunk_text(full_text)
                metadata = {
                    "type": "user_website",
                    "url": payload.url,
                    "firm_name": about_obj.get("firm_name"),
                    "user_id": user_info["id"],
                    "user_email": user_info["email"],
                    "description": payload.description,
                    "request_id": new_url_request.request_id
                }
                
                add_text_chunks_to_collection(chunks, metadata)
                
                # Mark as completed
                from datetime import datetime
                new_url_request.is_processed = True
                new_url_request.processing_status = "completed"
                if hasattr(new_url_request, 'status'):
                    new_url_request.status = "completed"
                if hasattr(new_url_request, 'processed_at'):
                    new_url_request.processed_at = datetime.now()
                new_url_request.notes = f"Successfully processed {len(chunks)} content chunks"
                if hasattr(new_url_request, 'content_type'):
                    new_url_request.content_type = "website"
                if hasattr(new_url_request, 'title'):
                    new_url_request.title = about_obj.get("firm_name", "")
                
                db.commit()
                
                return UserUrlResponse(
                    status="success",
                    message=f"🎉 URL processed successfully! Added {len(chunks)} content chunks to your chatbot's knowledge base. Your chatbot now knows about this website!"
                )
                
            except Exception as process_error:
                new_url_request.processing_status = "failed"
                if hasattr(new_url_request, 'status'):
                    new_url_request.status = "failed"
                new_url_request.notes = f"Processing error: {str(process_error)}"
                db.commit()
                return UserUrlResponse(
                    status="error",
                    message=f"Failed to process URL: {str(process_error)}"
                )
                
        finally:
            db.close()
            
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"❌ Submit URL error: {e}")
        return UserUrlResponse(
            status="error",
            message="Failed to submit URL"
        )

@app.get("/user/chat-urls")
async def get_user_chat_urls(user_id: Optional[int] = None, url_ids: Optional[str] = None):
    """Get user's processed URLs for chat widget"""
    try:
        db: Session = SessionLocal()
        try:
            from model.url_injection_models import URLInjectionRequest
            
            query = db.query(URLInjectionRequest).filter(
                URLInjectionRequest.status == "completed"
            )
            
            if user_id:
                query = query.filter(URLInjectionRequest.user_id == user_id)
            
            if url_ids:
                # Parse comma-separated URL IDs
                url_id_list = [int(id.strip()) for id in url_ids.split(',') if id.strip().isdigit()]
                if url_id_list:
                    query = query.filter(URLInjectionRequest.id.in_(url_id_list))
            
            urls = query.all()
            
            url_data = []
            for url in urls:
                firm_name = None
                if url.firm_id:
                    firm = db.query(Firm).filter(Firm.id == url.firm_id).first()
                    if firm:
                        firm_name = firm.name
                
                url_data.append({
                    "id": url.id,
                    "url": url.url,
                    "description": url.description,
                    "user_email": url.requester_email,
                    "firm_id": url.firm_id,
                    "firm_name": firm_name
                })
            
            return {
                "status": "success",
                "urls": url_data,
                "count": len(url_data)
            }
        finally:
            db.close()
            
    except Exception as e:
        return {
            "status": "error", 
            "message": f"Error fetching URLs: {str(e)}",
            "urls": []
        }

@app.get("/admin/stats")
async def get_admin_stats(request: Request):
    """Get admin dashboard statistics"""
    try:
        # Verify admin authentication
        auth_header = request.headers.get("authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="No valid authentication token")
        
        token = auth_header.split(" ")[1]
        valid, admin_info = admin_auth_service.validate_session(token)
        
        if not valid:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        
        db: Session = SessionLocal()
        try:
            from model.url_injection_models import URLInjectionRequest
            from model.user_models import User
            
            # URL injection stats
            total_requests = db.query(URLInjectionRequest).count()
            pending_requests = db.query(URLInjectionRequest).filter(
                URLInjectionRequest.status == "pending"
            ).count()
            approved_requests = db.query(URLInjectionRequest).filter(
                URLInjectionRequest.status == "approved"
            ).count()
            
            # User stats
            total_users = db.query(User).count()
            active_users = db.query(User).filter(User.is_active == True).count()
            users_with_urls = db.query(User.id).join(URLInjectionRequest).distinct().count()
            
            # Contact stats (if contacts model exists)
            total_contacts = 0
            try:
                total_contacts = db.query(Contact).count()
            except:
                pass
            
            # Firm stats (if firms model exists) 
            total_firms = 0
            try:
                total_firms = db.query(Firm).count()
            except:
                pass
            
            stats = {
                "url_requests": {
                    "total": total_requests,
                    "pending": pending_requests,
                    "approved": approved_requests,
                    "rejected": total_requests - pending_requests - approved_requests
                },
                "users": {
                    "total": total_users,
                    "active": active_users,
                    "with_urls": users_with_urls
                },
                "contacts": total_contacts,
                "firms": total_firms
            }
            
            return {"status": "success", "stats": stats}
        finally:
            db.close()
            
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"❌ Admin stats error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get statistics")

@app.get("/admin/users")
async def get_admin_users_list(request: Request):
    """Get list of all users for admin management"""
    try:
        # Verify admin authentication
        auth_header = request.headers.get("authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="No valid authentication token")
        
        token = auth_header.split(" ")[1]
        valid, admin_info = admin_auth_service.validate_session(token)
        
        if not valid:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        
        db: Session = SessionLocal()
        try:
            from model.user_models import User
            from model.url_injection_models import URLInjectionRequest
            
            # Get all users with URL submission count
            users = db.query(User).order_by(User.created_at.desc()).all()
            
            user_data = []
            for user in users:
                # Count URLs submitted by this user
                url_count = db.query(URLInjectionRequest).filter(
                    URLInjectionRequest.user_id == user.id
                ).count()
                
                user_data.append({
                    "id": user.id,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "full_name": user.full_name,
                    "email": user.email,
                    "phone": user.phone,
                    "url_count": url_count,
                    "is_active": user.is_active,
                    "is_verified": user.is_verified,
                    "created_at": user.created_at.isoformat(),
                    "last_login": user.last_login.isoformat() if user.last_login else None
                })
            
            return {"status": "success", "users": user_data}
        finally:
            db.close()
            
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"❌ Get admin users error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get users")
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

# User URL Management Admin Endpoints
@app.post("/admin/approve-user-url/{request_id}")
async def approve_user_url(request_id: str, request: Request):
    """Approve a user's URL request and process it"""
    admin_info = await verify_admin_auth(request)
    
    try:
        # First approve the request
        success, message = url_processing_service.approve_url_request(
            request_id, 
            admin_info.get('username', 'admin')
        )
        
        if not success:
            return {"status": "error", "message": message}
        
        # Then process the URL (scrape and add to vector store)
        process_success, process_message = await url_processing_service.process_url_request(
            request_id,
            admin_info.get('username', 'admin')
        )
        
        if process_success:
            return {
                "status": "success", 
                "message": f"URL approved and processed successfully. {process_message}"
            }
        else:
            return {
                "status": "partial_success",
                "message": f"URL approved but processing failed: {process_message}"
            }
            
    except Exception as e:
        return {"status": "error", "message": f"Error processing request: {str(e)}"}

@app.post("/admin/reject-user-url/{request_id}")
async def reject_user_url(request_id: str, request: Request, reason: str = None):
    """Reject a user's URL request"""
    admin_info = await verify_admin_auth(request)
    
    try:
        success, message = url_processing_service.reject_url_request(
            request_id,
            reason,
            admin_info.get('username', 'admin')
        )
        
        if success:
            return {"status": "success", "message": message}
        else:
            return {"status": "error", "message": message}
            
    except Exception as e:
        return {"status": "error", "message": f"Error rejecting request: {str(e)}"}

@app.get("/admin/user-urls")
async def get_user_url_requests(request: Request):
    """Get all user URL requests for admin management"""
    admin_info = await verify_admin_auth(request)
    
    try:
        db: Session = SessionLocal()
        try:
            from model.url_injection_models import URLInjectionRequest
            from model.user_models import User
            
            # Get all user-submitted URL requests
            url_requests = db.query(URLInjectionRequest).filter(
                URLInjectionRequest.user_id.isnot(None)
            ).order_by(URLInjectionRequest.created_at.desc()).all()
            
            user_urls = []
            for url_req in url_requests:
                # Get user info
                user = db.query(User).filter(User.id == url_req.user_id).first()
                user_name = f"{user.first_name} {user.last_name}" if user else "Unknown User"
                
                user_urls.append({
                    "id": url_req.id,
                    "request_id": url_req.request_id,
                    "url": url_req.url,
                    "description": url_req.description,
                    "status": url_req.status,
                    "processing_status": url_req.processing_status,
                    "user_name": user_name,
                    "user_email": url_req.requester_email,
                    "created_at": url_req.created_at.isoformat(),
                    "processed_at": url_req.processed_at.isoformat() if url_req.processed_at else None,
                    "processed_by": url_req.processed_by,
                    "notes": url_req.notes
                })
            
            return {
                "status": "success",
                "user_urls": user_urls,
                "total": len(user_urls)
            }
        finally:
            db.close()
            
    except Exception as e:
        return {"status": "error", "message": f"Error fetching user URLs: {str(e)}"}

@app.get("/admin/users")
async def get_admin_users(request: Request):
    """Get all users for admin management"""
    admin_info = await verify_admin_auth(request)
    
    try:
        db: Session = SessionLocal()
        try:
            from model.user_models import User
            from model.url_injection_models import URLInjectionRequest
            
            # Get all users
            users = db.query(User).order_by(User.created_at.desc()).all()
            
            user_data = []
            for user in users:
                # Count URLs for each user
                url_count = db.query(URLInjectionRequest).filter(
                    URLInjectionRequest.user_id == user.id
                ).count() if hasattr(URLInjectionRequest, 'user_id') else 0
                
                user_data.append({
                    "id": user.id,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "full_name": f"{user.first_name} {user.last_name}",
                    "email": user.email,
                    "phone": user.phone,
                    "is_active": user.is_active,
                    "created_at": user.created_at.isoformat(),
                    "last_login": user.last_login.isoformat() if user.last_login else None,
                    "url_count": url_count
                })
            
            return {
                "status": "success",
                "users": user_data,
                "total": len(user_data)
            }
        finally:
            db.close()
            
    except Exception as e:
        return {"status": "error", "message": f"Error fetching users: {str(e)}"}

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

