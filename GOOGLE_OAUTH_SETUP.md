# Google OAuth Configuration Guide

This guide will help you set up Google OAuth for the admin panel.

## Prerequisites

1. A Google Cloud Console project
2. OAuth 2.0 credentials configured
3. Environment variables set up

## Google Cloud Console Setup

### Step 1: Create a Project (if you don't have one)

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click "Select a project" → "New Project"
3. Enter project name and click "Create"

### Step 2: Enable Google+ API (optional, for profile info)

1. Go to "APIs & Services" → "Library"
2. Search for "Google+ API" or "People API"
3. Click "Enable"

### Step 3: Create OAuth 2.0 Credentials

1. Go to "APIs & Services" → "Credentials"
2. Click "Create Credentials" → "OAuth 2.0 Client IDs"
3. Choose "Web application"
4. Configure:
   - **Name**: "KitKool Admin OAuth"
   - **Authorized JavaScript origins**: 
     - `http://localhost:8000` (for development)
     - `https://yourdomain.com` (for production)
   - **Authorized redirect URIs**:
     - `http://localhost:8000/admin/oauth/callback` (for development)
     - `https://yourdomain.com/admin/oauth/callback` (for production)

### Step 4: Get Your Credentials

1. After creating, copy:
   - **Client ID**: looks like `123456789-xxxxx.apps.googleusercontent.com`
   - **Client Secret**: looks like `GOCSPX-xxxxxxxxxxxxxxxxxxxxx`

## Environment Configuration

### Step 1: Create .env file

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

### Step 2: Update OAuth Variables

Edit your `.env` file:

```env
# Google OAuth Configuration
GOOGLE_CLIENT_ID=your-actual-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-actual-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/admin/oauth/callback

# Update these for production
# GOOGLE_REDIRECT_URI=https://yourdomain.com/admin/oauth/callback
```

### Step 3: Other Required Variables

Make sure these are also set:

```env
SECRET_KEY=your-very-secure-secret-key-here
DATABASE_URL=sqlite:///./kitkool_bot.db
```

## Testing the Setup

1. Start your application:
   ```bash
   python mains.py
   ```

2. Navigate to: `http://localhost:8000/admin`

3. Try signing in with Google:
   - Click "Sign in with Google"
   - Authorize the application
   - You should be redirected back and logged in

## Troubleshooting

### Common Issues

1. **"redirect_uri_mismatch" error**:
   - Check that your redirect URI in Google Console exactly matches your .env file
   - Include the protocol (http/https)
   - Don't include trailing slashes

2. **"invalid_client" error**:
   - Check your Client ID and Client Secret
   - Make sure they're correctly copied (no extra spaces)

3. **"access_denied" error**:
   - User cancelled the authorization
   - Try again or use regular username/password login

### Development vs Production

**Development (localhost)**:
```env
GOOGLE_REDIRECT_URI=http://localhost:8000/admin/oauth/callback
```

**Production**:
```env
GOOGLE_REDIRECT_URI=https://yourdomain.com/admin/oauth/callback
```

Make sure to update Google Console with both URIs if you need both environments.

## Security Notes

1. **Never commit `.env` file** - it's already in `.gitignore`
2. **Use different credentials for production**
3. **Regularly rotate your Client Secret**
4. **Monitor OAuth usage in Google Console**

## Additional Features

### Restricting OAuth Access

To restrict which Google accounts can access your admin panel, you can:

1. **Domain restriction**: In Google Console → OAuth consent screen → Internal (for workspace accounts)
2. **Code-level restriction**: Modify `google_oauth_service.py` to check email domains

Example domain restriction in code:
```python
# In google_oauth_service.py, after getting user info
if not user_email.endswith('@yourdomain.com'):
    raise HTTPException(status_code=403, detail="Access restricted")
```

## Support

If you need help:
1. Check Google Cloud Console logs
2. Check your application logs
3. Verify all URLs are correctly configured
4. Test with a simple OAuth flow first