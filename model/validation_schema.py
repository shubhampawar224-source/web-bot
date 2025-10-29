from pydantic import BaseModel, HttpUrl
from typing import Optional, List

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)

        # ✅ Content Security Policy (CSP)
        # Adjust as needed if you load external scripts/fonts
        csp_policy = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self'; "
            "connect-src 'self' https:; "
            "frame-ancestors 'none'; "  # Prevent clickjacking
            "base-uri 'self'; "
            "form-action 'self';"
        )

        # ✅ Add security headers
        response.headers["Content-Security-Policy"] = csp_policy
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=(), payment=()"
        )
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"

        return response


# Request body schema
class URLPayload(BaseModel):
    url: HttpUrl
    tags: Optional[List[str]] = None
    session_id: Optional[str] = None  # optional if you want session-based storage

class ChatRequest(BaseModel):
    query: str
    session_id: str
    firm_id: str    


class ContactIn(BaseModel):
    fname: Optional[str] = None
    lname: Optional[str] = None
    email: Optional[str] = None
    phone_number: Optional[str] = None
    metadata: Optional[dict] = None



class ContactIn(BaseModel):
    fname: Optional[str] = None
    lname: Optional[str] = None
    email: Optional[str] = None
    phone_number: Optional[str] = None
    metadata: Optional[dict] = None
    notify_to: Optional[str] = None
