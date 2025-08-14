import { useState, useEffect } from 'react'
import { api, AuthStatus, ApiError } from './api'
import './App.css'

function App() {
  const [authStatus, setAuthStatus] = useState<AuthStatus>({ authenticated: false })
  const [loading, setLoading] = useState(true)
  const [apiResult, setApiResult] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Check authentication status on mount
  useEffect(() => {
    checkAuthStatus()
  }, [])

  const checkAuthStatus = async () => {
    try {
      setLoading(true)
      setError(null)
      const status = await api.getAuthStatus()
      setAuthStatus(status)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to check auth status')
    } finally {
      setLoading(false)
    }
  }

  const handleLogin = () => {
    setError(null)
    api.login()
  }

  const handleLogout = async () => {
    try {
      setError(null)
      await api.logout()
      setAuthStatus({ authenticated: false })
      setApiResult(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Logout failed')
    }
  }

  const handleApiCall = async () => {
    try {
      setError(null)
      setApiResult('Loading...')
      const result = await api.callProtectedApi()
      setApiResult(JSON.stringify(result, null, 2))
    } catch (err) {
      setApiResult(null)
      if (err instanceof ApiError && err.status === 401) {
        setError('Authentication required - please log in')
        setAuthStatus({ authenticated: false })
      } else {
        setError(err instanceof Error ? err.message : 'API call failed')
      }
    }
  }

  if (loading) {
    return (
      <div className="app">
        <div className="container">
          <h1>Ferentin OIDC Sample</h1>
          <div className="loading">Checking authentication status...</div>
        </div>
      </div>
    )
  }

  return (
    <div className="app">
      <div className="container">
        <header>
          <h1>Ferentin OIDC Sample</h1>
          <p>Demo of Authorization Code Flow with PKCE using BFF pattern</p>
        </header>

        <main>
          {error && (
            <div className="error">
              <strong>Error:</strong> {error}
              <button onClick={() => setError(null)} className="close-btn">×</button>
            </div>
          )}

          <section className="auth-section">
            <h2>Authentication Status</h2>
            {authStatus.authenticated ? (
              <div className="auth-info">
                <div className="status authenticated">✅ Authenticated</div>
                {authStatus.user && (
                  <div className="user-info">
                    <h3>User Information</h3>
                    <div className="user-details">
                      <div><strong>Subject:</strong> {authStatus.user.sub}</div>
                      {authStatus.user.name && (
                        <div><strong>Name:</strong> {authStatus.user.name}</div>
                      )}
                      {authStatus.user.email && (
                        <div><strong>Email:</strong> {authStatus.user.email}</div>
                      )}
                    </div>
                  </div>
                )}
                <div className="actions">
                  <button onClick={handleLogout} className="btn btn-secondary">
                    Logout
                  </button>
                  <button onClick={checkAuthStatus} className="btn btn-outline">
                    Refresh Status
                  </button>
                </div>
              </div>
            ) : (
              <div className="auth-info">
                <div className="status unauthenticated">❌ Not Authenticated</div>
                <div className="actions">
                  <button onClick={handleLogin} className="btn btn-primary">
                    Login with OIDC
                  </button>
                  <button onClick={checkAuthStatus} className="btn btn-outline">
                    Check Status
                  </button>
                </div>
              </div>
            )}
          </section>

          <section className="api-section">
            <h2>Protected API Call</h2>
            <p>Test calling a protected API endpoint through the BFF</p>
            
            <div className="actions">
              <button 
                onClick={handleApiCall} 
                className="btn btn-primary"
                disabled={!authStatus.authenticated}
              >
                Call Protected API
              </button>
            </div>

            {apiResult && (
              <div className="api-result">
                <h3>API Response:</h3>
                <pre>{apiResult}</pre>
              </div>
            )}
          </section>

          <section className="info-section">
            <h2>How it Works</h2>
            <ol>
              <li><strong>Login:</strong> Redirects to OIDC provider via BFF</li>
              <li><strong>Callback:</strong> BFF exchanges code for tokens using PKCE</li>
              <li><strong>Session:</strong> BFF stores tokens server-side, issues HTTP-only cookie</li>
              <li><strong>API Calls:</strong> SPA calls BFF endpoints, BFF uses stored tokens</li>
              <li><strong>Security:</strong> Tokens never exposed to browser, CSRF protection enabled</li>
            </ol>
          </section>
        </main>

        <footer>
          <p>
            <strong>Backend:</strong> Python FastAPI running on :8000 |{' '}
            <strong>Frontend:</strong> React + Vite running on :5173
          </p>
        </footer>
      </div>
    </div>
  )
}

export default App
