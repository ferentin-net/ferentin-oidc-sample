"""
FastAPI Backend-for-Frontend (BFF) implementing OIDC Authorization Code Flow with PKCE.

This BFF handles:
- OIDC login/logout flows
- Token management (server-side only)
- Session management with HTTP-only cookies
- CSRF protection
- API proxying to protected resources
"""

import os
import secrets
import time
import urllib.parse
from typing import Any, Dict, Optional

import httpx
from fastapi import FastAPI, HTTPException, Request, Response, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from dotenv import load_dotenv
from itsdangerous import URLSafeTimedSerializer, BadSignature
from jose import jwt, JWTError

# Load environment variables
load_dotenv()

# Configuration
OIDC_ISSUER = os.getenv("OIDC_ISSUER")
OIDC_CLIENT_ID = os.getenv("OIDC_CLIENT_ID")
OIDC_CLIENT_SECRET = os.getenv("OIDC_CLIENT_SECRET")
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
REDIRECT_PATH = os.getenv("REDIRECT_PATH", "/bff/callback")
SESSION_SECRET_KEY = os.getenv("SESSION_SECRET_KEY", "change-this-in-production")
API_BASE_URL = os.getenv("API_BASE_URL")
OIDC_SCOPES = os.getenv("OIDC_SCOPES", "openid profile email")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "lax")

# Validate required configuration
if not all([OIDC_ISSUER, OIDC_CLIENT_ID]):
    raise ValueError("OIDC_ISSUER and OIDC_CLIENT_ID are required")

app = FastAPI(title="Ferentin OIDC BFF", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Session storage (in-memory for demo - use Redis/database in production)
sessions: Dict[str, Dict[str, Any]] = {}

# OIDC Discovery cache
oidc_config: Optional[Dict[str, Any]] = None
jwks_cache: Optional[Dict[str, Any]] = None

# Utilities
serializer = URLSafeTimedSerializer(SESSION_SECRET_KEY)

class OIDCError(Exception):
    """Custom exception for OIDC-related errors."""
    pass

async def get_oidc_config() -> Dict[str, Any]:
    """Fetch and cache OIDC discovery configuration."""
    global oidc_config
    if oidc_config is None:
        discovery_url = f"{OIDC_ISSUER.rstrip('/')}/.well-known/openid-configuration"
        async with httpx.AsyncClient() as client:
            response = await client.get(discovery_url)
            if response.status_code != 200:
                raise OIDCError(f"Failed to fetch OIDC config: {response.status_code}")
            oidc_config = response.json()
    return oidc_config

async def get_jwks() -> Dict[str, Any]:
    """Fetch and cache JWKS for token validation."""
    global jwks_cache
    if jwks_cache is None:
        config = await get_oidc_config()
        jwks_uri = config.get("jwks_uri")
        if not jwks_uri:
            raise OIDCError("No jwks_uri in OIDC config")
        
        async with httpx.AsyncClient() as client:
            response = await client.get(jwks_uri)
            if response.status_code != 200:
                raise OIDCError(f"Failed to fetch JWKS: {response.status_code}")
            jwks_cache = response.json()
    return jwks_cache

def generate_pkce_challenge() -> tuple[str, str]:
    """Generate PKCE code verifier and challenge."""
    code_verifier = secrets.token_urlsafe(32)
    # For simplicity, using plain method (should use S256 in production)
    code_challenge = code_verifier
    return code_verifier, code_challenge

def create_session(user_info: Dict[str, Any], tokens: Dict[str, Any]) -> str:
    """Create a new session and return session ID."""
    session_id = secrets.token_urlsafe(32)
    sessions[session_id] = {
        "user": user_info,
        "tokens": tokens,
        "created_at": time.time(),
        "csrf_token": secrets.token_urlsafe(32)
    }
    return session_id

def get_session_from_request(request: Request) -> Optional[Dict[str, Any]]:
    """Extract session from request cookies."""
    session_cookie = request.cookies.get("sid")
    if not session_cookie:
        return None
    
    try:
        session_id = serializer.loads(session_cookie, max_age=24*3600)  # 24 hours
        return sessions.get(session_id)
    except BadSignature:
        return None

def require_session(request: Request) -> Dict[str, Any]:
    """Dependency to require valid session."""
    session = get_session_from_request(request)
    if not session:
        raise HTTPException(status_code=401, detail="Authentication required")
    return session

def require_csrf(request: Request, session: Dict[str, Any] = Depends(require_session)) -> None:
    """Dependency to require valid CSRF token for write operations."""
    csrf_header = request.headers.get("X-CSRF-Token")
    expected_csrf = session.get("csrf_token")
    
    if not csrf_header or not expected_csrf or csrf_header != expected_csrf:
        raise HTTPException(status_code=403, detail="Invalid CSRF token")

async def refresh_tokens_if_needed(session: Dict[str, Any]) -> None:
    """Refresh access token if it's close to expiry."""
    tokens = session.get("tokens", {})
    refresh_token = tokens.get("refresh_token")
    expires_at = tokens.get("expires_at", 0)
    
    # Refresh if token expires in less than 5 minutes
    if not refresh_token or time.time() < (expires_at - 300):
        return
    
    try:
        config = await get_oidc_config()
        token_endpoint = config.get("token_endpoint")
        
        token_data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": OIDC_CLIENT_ID,
        }
        
        if OIDC_CLIENT_SECRET:
            token_data["client_secret"] = OIDC_CLIENT_SECRET
        
        async with httpx.AsyncClient() as client:
            response = await client.post(token_endpoint, data=token_data)
            if response.status_code == 200:
                new_tokens = response.json()
                # Update session with new tokens
                session["tokens"].update(new_tokens)
                if "expires_in" in new_tokens:
                    session["tokens"]["expires_at"] = time.time() + new_tokens["expires_in"]
    except Exception:
        # If refresh fails, let the session expire naturally
        pass

# Routes

@app.get("/")
async def root():
    """Health check endpoint."""
    return {"message": "Ferentin OIDC BFF is running"}

@app.get("/bff/login")
async def login(request: Request):
    """Initiate OIDC login flow."""
    try:
        config = await get_oidc_config()
        authorization_endpoint = config.get("authorization_endpoint")
        
        if not authorization_endpoint:
            raise OIDCError("No authorization_endpoint in OIDC config")
        
        # Generate PKCE parameters
        code_verifier, code_challenge = generate_pkce_challenge()
        temp_session_id = secrets.token_urlsafe(16)
        
        # Encode temp_session_id in the state parameter
        state_data = {
            "temp_session": temp_session_id,
            "random": secrets.token_urlsafe(16)
        }
        state = serializer.dumps(state_data)
        
        # Store PKCE parameters in temporary session
        sessions[f"temp_{temp_session_id}"] = {
            "code_verifier": code_verifier,
            "state": state,
            "created_at": time.time()
        }
        
        # Build authorization URL
        params = {
            "response_type": "code",
            "client_id": OIDC_CLIENT_ID,
            "redirect_uri": f"{request.url.scheme}://{request.url.netloc}{REDIRECT_PATH}",
            "scope": OIDC_SCOPES,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "plain",  # Use S256 in production
        }
        
        auth_url = f"{authorization_endpoint}?{urllib.parse.urlencode(params)}"
        return RedirectResponse(url=auth_url)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")

@app.get("/bff/callback")
async def callback(request: Request, code: str, state: str):
    """Handle OIDC callback and exchange code for tokens."""
    try:
        # Decode state parameter to get temp_session
        try:
            state_data = serializer.loads(state, max_age=600)  # 10 minutes max
            temp_session_id = state_data.get("temp_session")
        except BadSignature:
            raise OIDCError("Invalid or expired state parameter")
        
        if not temp_session_id:
            raise OIDCError("Missing temp_session in state")
        
        # Retrieve temporary session
        temp_session_data = sessions.get(f"temp_{temp_session_id}")
        if not temp_session_data:
            raise OIDCError("Invalid or expired temporary session")
        
        # Verify state parameter matches what we stored
        if state != temp_session_data.get("state"):
            raise OIDCError("Invalid state parameter")
        
        # Clean up temporary session
        sessions.pop(f"temp_{temp_session_id}", None)
        
        config = await get_oidc_config()
        token_endpoint = config.get("token_endpoint")
        
        # Exchange code for tokens
        token_data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": f"{request.url.scheme}://{request.url.netloc}{REDIRECT_PATH}",
            "client_id": OIDC_CLIENT_ID,
            "code_verifier": temp_session_data["code_verifier"],
        }
        
        if OIDC_CLIENT_SECRET:
            token_data["client_secret"] = OIDC_CLIENT_SECRET
        
        async with httpx.AsyncClient() as client:
            response = await client.post(token_endpoint, data=token_data)
            if response.status_code != 200:
                raise OIDCError(f"Token exchange failed: {response.status_code}")
            
            tokens = response.json()
        
        # Extract user info from ID token
        id_token = tokens.get("id_token")
        if not id_token:
            raise OIDCError("No ID token received")
        
        # Decode ID token (simplified - should validate signature in production)
        try:
            user_info = jwt.get_unverified_claims(id_token)
        except JWTError:
            raise OIDCError("Invalid ID token")
        
        # Add token expiry time
        if "expires_in" in tokens:
            tokens["expires_at"] = time.time() + tokens["expires_in"]
        
        # Create session
        session_id = create_session(user_info, tokens)
        session_cookie = serializer.dumps(session_id)
        
        # Create response with cookies
        response = RedirectResponse(url=FRONTEND_ORIGIN)
        response.set_cookie(
            key="sid",
            value=session_cookie,
            httponly=True,
            secure=COOKIE_SECURE,
            samesite=COOKIE_SAMESITE,
            max_age=24*3600  # 24 hours
        )
        response.set_cookie(
            key="csrf",
            value=sessions[session_id]["csrf_token"],
            secure=COOKIE_SECURE,
            samesite=COOKIE_SAMESITE,
            max_age=24*3600  # 24 hours
        )
        
        return response
        
    except OIDCError as e:
        # Redirect to frontend with OIDC-specific error
        error_url = f"{FRONTEND_ORIGIN}?error={urllib.parse.quote(f'OIDC Error: {str(e)}')}"
        return RedirectResponse(url=error_url)
    except Exception as e:
        # Redirect to frontend with general error
        error_url = f"{FRONTEND_ORIGIN}?error={urllib.parse.quote(f'Authentication failed: {str(e)}')}"
        return RedirectResponse(url=error_url)

@app.get("/bff/me")
async def get_user_info(session: Dict[str, Any] = Depends(require_session)):
    """Get current user information."""
    await refresh_tokens_if_needed(session)
    return session.get("user", {})

@app.post("/bff/logout")
async def logout(request: Request, _: None = Depends(require_csrf)):
    """Logout user and clear session."""
    session = get_session_from_request(request)
    
    if session:
        # Find and remove session
        for session_id, stored_session in list(sessions.items()):
            if stored_session == session:
                sessions.pop(session_id, None)
                break
    
    # Clear cookies
    response = Response(status_code=200)
    response.set_cookie(
        key="sid",
        value="",
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        expires=0
    )
    response.set_cookie(
        key="csrf",
        value="",
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        expires=0
    )
    
    return {"message": "Logged out successfully"}

@app.get("/bff/api/example")
async def protected_api_example(session: Dict[str, Any] = Depends(require_session)):
    """Example protected API endpoint."""
    await refresh_tokens_if_needed(session)
    
    user = session.get("user", {})
    tokens = session.get("tokens", {})
    
    return {
        "message": "This is a protected API endpoint",
        "user_id": user.get("sub"),
        "timestamp": time.time(),
        "token_type": tokens.get("token_type", "Bearer"),
        "has_access_token": bool(tokens.get("access_token")),
        "example_data": {
            "protected_resource": "This data requires authentication",
            "user_specific_info": f"Hello, {user.get('name', user.get('sub', 'User'))}!"
        }
    }

@app.api_route("/bff/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy_api(
    path: str,
    request: Request,
    session: Dict[str, Any] = Depends(require_session),
    _: None = Depends(lambda r, s=Depends(require_session): require_csrf(r, s) if r.method in ["POST", "PUT", "DELETE", "PATCH"] else None)
):
    """Proxy API calls to protected backend services."""
    if not API_BASE_URL:
        raise HTTPException(status_code=501, detail="API proxying not configured")
    
    await refresh_tokens_if_needed(session)
    
    tokens = session.get("tokens", {})
    access_token = tokens.get("access_token")
    
    if not access_token:
        raise HTTPException(status_code=401, detail="No access token available")
    
    # Prepare headers
    headers = dict(request.headers)
    headers["Authorization"] = f"Bearer {access_token}"
    
    # Remove problematic headers
    headers.pop("host", None)
    headers.pop("content-length", None)
    
    # Prepare request
    url = f"{API_BASE_URL.rstrip('/')}/{path.lstrip('/')}"
    body = await request.body() if request.method in ["POST", "PUT", "PATCH"] else None
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method=request.method,
                url=url,
                headers=headers,
                params=request.query_params,
                content=body,
                timeout=30.0
            )
            
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=dict(response.headers)
            )
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"API request failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
