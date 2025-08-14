// API client for communicating with the BFF

export interface User {
  sub: string;
  name?: string;
  email?: string;
  [key: string]: any;
}

export interface AuthStatus {
  authenticated: boolean;
  user?: User;
}

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

class ApiClient {
  private csrfToken: string | null = null;

  constructor(private baseUrl: string = '') {}

  private async getCsrfToken(): Promise<string> {
    if (this.csrfToken) {
      return this.csrfToken;
    }

    // CSRF token is sent as a readable cookie by the backend
    const cookies = document.cookie.split(';');
    for (const cookie of cookies) {
      const [name, value] = cookie.trim().split('=');
      if (name === 'csrf') {
        this.csrfToken = decodeURIComponent(value);
        return this.csrfToken;
      }
    }

    throw new Error('CSRF token not found');
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...Object.fromEntries(
        Object.entries(options.headers || {}).map(([k, v]) => [k, String(v)])
      ),
    };

    // Add CSRF token for non-GET requests
    if (options.method && options.method !== 'GET') {
      try {
        headers['X-CSRF-Token'] = await this.getCsrfToken();
      } catch (error) {
        console.warn('Could not get CSRF token:', error);
      }
    }

    const response = await fetch(url, {
      ...options,
      headers,
      credentials: 'include', // Include cookies
    });

    if (!response.ok) {
      let errorMessage = `HTTP ${response.status}`;
      try {
        const errorData = await response.json();
        errorMessage = errorData.detail || errorData.message || errorMessage;
      } catch {
        // Use default error message if response isn't JSON
      }
      throw new ApiError(response.status, errorMessage);
    }

    // Handle empty responses
    const contentType = response.headers.get('content-type');
    if (!contentType || !contentType.includes('application/json')) {
      return {} as T;
    }

    return response.json();
  }

  // Authentication endpoints
  async getAuthStatus(): Promise<AuthStatus> {
    try {
      const user = await this.request<User>('/bff/me');
      return { authenticated: true, user };
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        return { authenticated: false };
      }
      throw error;
    }
  }

  login(): void {
    // Redirect to login endpoint
    window.location.href = '/bff/login';
  }

  async logout(): Promise<void> {
    await this.request('/bff/logout', { method: 'POST' });
    // Clear cached CSRF token
    this.csrfToken = null;
  }

  // Example protected API call
  async callProtectedApi(): Promise<any> {
    return this.request('/bff/api/example');
  }

  // Generic API proxy method
  async apiCall<T>(path: string, options: RequestInit = {}): Promise<T> {
    return this.request<T>(`/bff/api${path}`, options);
  }
}

export const api = new ApiClient();
export { ApiError };
