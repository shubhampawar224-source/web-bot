# 🔐 URL Injection Email Confirmation System

This document explains the new email-based authorization system for URL injection in the Web Assistant.

## 🎯 Overview

The URL injection feature now requires email confirmation to ensure only authorized users can add content to the assistant's knowledge base. This prevents unauthorized access and maintains content quality.

## 🔧 Setup Instructions

### 1. Configure Email Settings

Copy the email configuration template:
```bash
cp .env.email.template .env.local
```

Add these settings to your `.env` file:
```env
# Gmail SMTP Configuration
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASS=your-app-password
FROM_EMAIL=your-email@gmail.com

# Application Base URL
WIDGET_BASE_URL=http://127.0.0.1:8000
```

### 2. Generate Gmail App Password

1. Go to [Google Account Security Settings](https://myaccount.google.com/security)
2. Enable **2-Step Verification** (required)
3. Go to **App passwords** 
4. Generate a new app password for "Mail"
5. Use the 16-character password as `SMTP_PASS`

### 3. Install Required Dependencies

The email system uses `python-dotenv` which should already be in your requirements:
```bash
pip install python-dotenv
```

## 🚀 How It Works

### User Workflow:

1. **Request URL Injection**: User enters URL and email in the sidebar
2. **Email Sent**: System sends confirmation email with secure token
3. **Email Confirmation**: User clicks confirmation link in email
4. **URL Processed**: System automatically scrapes and adds URL to knowledge base

### Technical Flow:

1. `POST /request-url-injection` - Creates pending request
2. Email sent with confirmation link containing unique token
3. `GET /confirm-url-injection/{token}` - Validates and confirms request
4. Background task processes confirmed URLs using existing scraper

## 📧 Email Template Features

The confirmation email includes:

- ✅ Professional HTML styling
- 🔒 Security warnings and guidelines  
- ⏰ 24-hour expiration notice
- 🌐 Clear URL display
- 📊 Request tracking information
- 📱 Mobile-friendly responsive design

## 🛡️ Security Features

### Token Security:
- **Cryptographically secure**: Uses `secrets.token_urlsafe(32)`
- **Time-limited**: 24-hour automatic expiration
- **Single-use**: Tokens cannot be reused after confirmation
- **Request tracking**: Full audit trail with timestamps

### Validation:
- **Email format validation**: Server-side email format checking
- **URL validation**: Pydantic HttpUrl validation
- **Duplicate prevention**: Checks for existing URLs and pending requests
- **Error handling**: Comprehensive error messages and logging

## 🎨 Frontend Enhancements

### Updated Sidebar:
- **Email input field**: Required for URL injection requests
- **Enhanced messaging**: Clear feedback on request status
- **Improved validation**: Client-side email format checking
- **Better UX**: Loading states and success confirmations

### Toast Notifications:
- **Enhanced styling**: Success/error state indicators
- **Longer messages**: Support for detailed confirmation instructions
- **Better positioning**: Improved responsive positioning
- **Duration control**: Configurable display duration

## 🔍 API Endpoints

### Request URL Injection
```http
POST /request-url-injection
Content-Type: application/json

{
    "url": "https://example.com/page",
    "email": "user@example.com"
}
```

**Response:**
```json
{
    "status": "success",
    "message": "Confirmation email sent to user@example.com. Please check your inbox and click the confirmation link.",
    "request_id": "unique-request-id"
}
```

### Confirm URL Injection
```http
GET /confirm-url-injection/{token}
```

Returns HTML confirmation page with success/error message.

### Get Pending Requests (Admin)
```http
GET /pending-url-requests
```

Returns list of all confirmed but unprocessed URL requests.

## 📊 Database Schema

### URLInjectionRequest Model:
```python
class URLInjectionRequest(Base):
    request_id: str           # Unique identifier
    url: str                  # Requested URL
    requester_email: str      # User's email
    confirmation_token: str   # Secure confirmation token
    is_confirmed: bool        # Confirmation status
    is_processed: bool        # Processing status
    created_at: datetime      # Request timestamp
    confirmed_at: datetime    # Confirmation timestamp
    expires_at: datetime      # Token expiration (24h)
```

## 🔧 Configuration Options

### Environment Variables:
- `SMTP_HOST`: Mail server hostname (default: smtp.gmail.com)
- `SMTP_PORT`: Mail server port (default: 587)
- `SMTP_USER`: Email account username
- `SMTP_PASS`: Email account password/app password
- `FROM_EMAIL`: Sender email address
- `WIDGET_BASE_URL`: Base URL for confirmation links

### Customization:
- **Email templates**: Modify HTML/text in `url_confirmation_service.py`
- **Token expiration**: Adjust `timedelta(hours=24)` in models
- **Validation rules**: Update email/URL validation patterns
- **Styling**: Customize email CSS and frontend toast styles

## 🐛 Troubleshooting

### Common Issues:

**Email not sending:**
- Verify Gmail App Password is correct
- Check 2-Step Verification is enabled
- Ensure SMTP credentials in `.env` are correct
- Check server logs for SMTP errors

**Confirmation link not working:**
- Verify `WIDGET_BASE_URL` is correct
- Check token hasn't expired (24h limit)
- Ensure database is properly initialized
- Check for network connectivity issues

**URL not being processed:**
- Confirm URL was successfully confirmed
- Check background task execution
- Verify scraper functionality
- Check database connection

### Debug Commands:

```bash
# Test email configuration
python -c "from utils.url_confirmation_service import url_confirmation_service; print('Email service initialized')"

# Check pending requests
curl http://localhost:8000/pending-url-requests

# Verify database tables
python -c "from database.db import init_db; init_db(); print('DB initialized')"
```

## 🚀 Future Enhancements

Potential improvements:
- **Admin dashboard**: Web interface for managing requests
- **Bulk processing**: Handle multiple URLs in single request
- **Email notifications**: Status updates to requesters
- **Rate limiting**: Prevent spam/abuse
- **Integration**: Webhook support for external systems

## 📝 Logs and Monitoring

The system logs important events:
- ✅ Email send success/failure
- 🔄 URL processing status
- ❌ Validation errors
- 🔍 Request tracking

Monitor logs for:
```bash
# Email sending
grep "Confirmation email sent" app.log

# URL processing
grep "Processing confirmed URL" app.log

# Errors
grep "ERROR\|Failed" app.log
```

---

**Need help?** Check the troubleshooting section or review the server logs for detailed error information.