# Ferentin Python BFF Sample

A Python FastAPI Backend-for-Frontend (BFF) that implements OIDC Authorization Code Flow with PKCE.

## Features

- **OIDC Authorization Code Flow with PKCE** for secure authentication
- **Server-side token storage** - access/refresh tokens never exposed to browser
- **HTTP-only cookies** for session management
- **CSRF protection** with dedicated tokens
- **Automatic token refresh** when access tokens near expiry
- **API proxying** to protected backend services
- **Production-ready security defaults**

## Quick Start

### 1. Setup Python Environment

```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
# Copy environment template
cp env.example .env

# Edit .env with your OIDC provider settings
```

### 3. Environment Variables

Configure your `.env` file with the following variables:

```bash
# Required
OIDC_ISSUER=https://your-oidc-provider.com
OIDC_CLIENT_ID=your-client-id

# Optional but recommended
OIDC_CLIENT_SECRET=your-client-secret
SESSION_SECRET_KEY=your-random-secret-key

# Application settings
FRONTEND_ORIGIN=http://localhost:5173
REDIRECT_PATH=/bff/callback

# Optional API proxying
API_BASE_URL=https://your-api.com

# Optional custom scopes (defaults to "openid profile email")
OIDC_SCOPES=openid profile email

# Production cookie settings
COOKIE_SECURE=false  # Set to true in production with HTTPS
COOKIE_SAMESITE=Lax  # Use None with Secure=true for cross-site
```

### 4. OIDC Provider Configuration

Configure your OIDC provider with these settings:

- **Redirect URI**: `http://localhost:8000/bff/callback`
- **Allowed Origins**: `http://localhost:5173` (for CORS)
- **Grant Types**: Authorization Code
- **Response Types**: code
- **PKCE**: Required/Enabled

### 5. Start the Server

```bash
# Using the provided script
./run.sh

# Or directly with uvicorn
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The BFF will start on `http://localhost:8000`

## API Endpoints

### Authentication Endpoints

- `GET /bff/login` - Initiate OIDC login flow
- `GET /bff/callback` - Handle OIDC callback
- `GET /bff/me` - Get current user information
- `POST /bff/logout` - Logout and clear session

### Protected API Endpoints

- `GET /bff/api/example` - Example protected endpoint
- `ALL /bff/api/*` - Proxy to configured API backend

## Security Features

### Session Management

- Sessions stored server-side (in-memory for demo)
- HTTP-only cookies prevent XSS attacks
- Signed session IDs with expiration
- Automatic cleanup of expired sessions

### CSRF Protection

- Separate readable `csrf` cookie for frontend
- `X-CSRF-Token` header required for write operations
- Token validation on all POST/PUT/DELETE requests

### Token Management

- Access/refresh tokens stored server-side only
- Automatic token refresh before expiry
- Secure token exchange with PKCE
- No tokens exposed to browser JavaScript

### Cookie Security

- `HttpOnly` flag prevents JavaScript access
- `Secure` flag for HTTPS in production
- `SameSite` attribute for CSRF protection
- Configurable security levels per environment

## Development

### Running in Development

```bash
# With auto-reload
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# With debug logging
uvicorn main:app --reload --host 0.0.0.0 --port 8000 --log-level debug
```

### Testing with curl

```bash
# Check health
curl http://localhost:8000/

# Start login flow (will redirect)
curl -i http://localhost:8000/bff/login

# Check auth status (requires session cookie)
curl -b cookies.txt http://localhost:8000/bff/me

# Call protected API
curl -b cookies.txt http://localhost:8000/bff/api/example
```

## Production Deployment

### Environment Configuration

```bash
# Production settings
COOKIE_SECURE=true
COOKIE_SAMESITE=None
SESSION_SECRET_KEY=your-strong-random-key
FRONTEND_ORIGIN=https://your-spa-domain.com
```

### Security Considerations

1. **HTTPS Only**: Use HTTPS in production
2. **Strong Secrets**: Generate cryptographically strong session keys
3. **Session Storage**: Use Redis or database instead of in-memory storage
4. **Token Validation**: Implement proper JWT signature validation
5. **CORS**: Configure strict CORS policies
6. **Rate Limiting**: Add rate limiting for auth endpoints
7. **Logging**: Implement security event logging

### Docker Deployment

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## Architecture

### Flow Diagram

```
1. Frontend requests /bff/login
2. BFF redirects to OIDC provider with PKCE
3. User authenticates with OIDC provider
4. OIDC provider redirects to /bff/callback with code
5. BFF exchanges code for tokens using PKCE
6. BFF stores tokens server-side, issues session cookie
7. Frontend makes API calls with session cookie
8. BFF validates session, proxies API calls with access token
```

### Session Structure

```python
{
    "user": {
        "sub": "user-id",
        "name": "User Name",
        "email": "user@example.com"
    },
    "tokens": {
        "access_token": "...",
        "refresh_token": "...",
        "expires_at": 1234567890
    },
    "csrf_token": "random-csrf-token",
    "created_at": 1234567890
}
```

## Troubleshooting

### Common Issues

1. **OIDC Discovery Failed**
   - Check OIDC_ISSUER URL is correct
   - Ensure `/.well-known/openid-configuration` is accessible

2. **Invalid Redirect URI**
   - Verify redirect URI matches exactly in OIDC provider
   - Check protocol (http vs https) and port numbers

3. **CORS Errors**
   - Ensure FRONTEND_ORIGIN matches your SPA's URL
   - Check OIDC provider allows your domain

4. **Token Exchange Failed**
   - Verify client credentials are correct
   - Check PKCE is enabled in OIDC provider
   - Ensure authorization code hasn't expired

5. **Session Not Working**
   - Check cookie settings for your environment
   - Verify SESSION_SECRET_KEY is set
   - Ensure frontend includes credentials in requests

### Debug Mode

Enable debug logging to troubleshoot issues:

```bash
export PYTHONPATH=$PYTHONPATH:.
python -c "
import logging
logging.basicConfig(level=logging.DEBUG)
import uvicorn
uvicorn.run('main:app', host='0.0.0.0', port=8000, log_level='debug')
"
```

## Contributing

This is a reference implementation for educational purposes. For production use:

1. Implement proper error handling and logging
2. Add comprehensive tests
3. Use production-grade session storage
4. Implement proper JWT validation
5. Add monitoring and metrics
6. Follow security best practices for your environment
