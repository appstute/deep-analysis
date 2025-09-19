import axios, { AxiosError, AxiosResponse, InternalAxiosRequestConfig } from 'axios';
import { storageService } from './storageService';

// Counter to track ongoing requests
let requestCounter = 0;

// Custom event for loader state changes
const LOADER_EVENT = 'api-loader-state-change';

const updateLoaderState = () => {
  // Only show loader if there are active requests
  const isLoading = requestCounter > 0;
  console.log('🔄 Loader state:', { requestCounter, isLoading });
  window.dispatchEvent(new CustomEvent(LOADER_EVENT, { detail: { isLoading } }));
};

// Helper to check if loader should be shown for this request
const shouldShowLoader = (url: string | undefined): boolean => {
  if (!url) return false;
  
  // Skip loader for these endpoints
  const skipLoaderEndpoints = [
    'oauth2.googleapis.com',
    '/refresh_token',
    '/analyze',  // Keep for legacy compatibility
    '/create_job',
    '/token-history'  // Skip loader for job creation (shows custom job status instead)
  ];
  
  return !skipLoaderEndpoints.some(endpoint => url.includes(endpoint));
};

// Global unauthorized handler
const globalUnauthorizedHandler = (status: number): boolean => {
  console.log(`[GlobalUnauthorizedHandler] Handling status: ${status}`);
  
  // Force logout for any unauthorized access
  const forceLogout = (reason: string) => {
    console.warn('[GlobalUnauthorizedHandler] Force logout:', reason);
    
    // Dispatch force logout event
    window.dispatchEvent(new CustomEvent('force-logout', { 
      detail: { reason } 
    }));
    
    return true;
  };

  if (status === 401) {
    return forceLogout('Token expired or invalid (401)');
  }
  
  if (status === 403) {
    return forceLogout('Access forbidden (403)');
  }
  
  return false;
};

// Create axios instance
const apiClient = axios.create({
  baseURL: import.meta.env.VITE_APP_API_URL || 'http://192.168.0.88:5000',
  headers: {
    'Content-Type': 'application/json',
  },
});

// Helper function to build EventSource URL with auth token
export const buildEventSourceUrl = (path: string): string => {
  try {
    const user = storageService.getUser();
    if (!user) {
      throw new Error('No user data found');
    }

    const baseUrl = import.meta.env.VITE_APP_API_URL || '';
    const url = new URL(path, baseUrl);
    url.searchParams.append('token', user.id_token || user.token || '');
    return url.toString();
  } catch (error) {
    console.error('[API] Failed to get user data from encrypted storage for EventSource URL:', error);
    throw new Error('Failed to build EventSource URL - user authentication required');
  }
};

// Request interceptor
apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig): InternalAxiosRequestConfig => {
    // Check if we should show loader for this request
    if (shouldShowLoader(config.url)) {
      requestCounter++;
      updateLoaderState();
      console.log('🚀 Request started:', {
        url: config.url,
        method: config.method,
        activeRequests: requestCounter,
        showingLoader: true
      });
    } else {
      console.log('🚀 Request started (no loader):', {
        url: config.url,
        method: config.method
      });
    }

    try {
      const user = storageService.getUser();
      if (user) {
        if (config.headers && user.id_token) {
          config.headers.Authorization = `Bearer ${user.id_token}`;
        }
      }
    } catch (error) {
      console.error('[API] Failed to get user data from encrypted storage for auth header:', error);
    }
    return config;
  },
  (error: AxiosError) => {
    // Decrement counter and update loader on request error
    if (error.config && shouldShowLoader(error.config.url)) {
      requestCounter = Math.max(0, requestCounter - 1);
      updateLoaderState();
      console.log('❌ Request error:', {
        error: error.message,
        activeRequests: requestCounter
      });
    }
    return Promise.reject(error);
  }
);

// Response interceptor
apiClient.interceptors.response.use(
  (response: AxiosResponse) => {
    // Decrement counter and update loader on successful response
    if (shouldShowLoader(response.config.url)) {
      requestCounter = Math.max(0, requestCounter - 1);
      updateLoaderState();
      console.log('✅ Request completed:', {
        url: response.config.url,
        activeRequests: requestCounter,
        showingLoader: true
      });
    } else {
      console.log('✅ Request completed (no loader):', {
        url: response.config.url
      });
    }
    return response;
  },
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean };
    
    // Decrement counter and update loader on response error
    if (error.config && shouldShowLoader(error.config.url)) {
      requestCounter = Math.max(0, requestCounter - 1);
      updateLoaderState();
      console.log('❌ Request failed:', {
        url: error.config.url,
        activeRequests: requestCounter
      });
    }

    if (!originalRequest) {
      return Promise.reject(error);
    }

    // Handle 401/403 errors with global unauthorized handler
    if ((error.response?.status === 401 || error.response?.status === 403) && !originalRequest._retry) {
      originalRequest._retry = true;
      
      console.log(`🔄 Unauthorized (${error.response?.status}) - attempting recovery...`);
      
      // Try token refresh first if we have a refresh token
      const user = storageService.getUser();
      if (user) {
        try {
          // Only attempt refresh token flow if we have a refresh token
          if (user.refresh_token) {
            console.log('🔄 Attempting token refresh...');
            
            // Get new tokens using refresh token
            const response = await axios.post(`${import.meta.env.VITE_APP_API_URL}/refresh_token`, {
              refresh_token: user.refresh_token,
            });

            const { access_token, id_token } = response.data;

            // Get new token expiration
            const tokenInfo = await axios.get<{ exp: number }>(
              `https://oauth2.googleapis.com/tokeninfo?id_token=${id_token}`
            );

            
            // Update stored tokens while preserving role and other user data
            const updatedUser = {
              ...user, // Preserve all existing user data including role
              access_token,
              id_token,
              exp: tokenInfo.data.exp,
              // Preserve role from backend response if provided
              ...(response.data.role && { role: response.data.role }),
            };
            console.log("updatedUser", updatedUser);
          
            storageService.setUser(updatedUser);

            // Update auth header with new token
            if (originalRequest.headers) {
              originalRequest.headers.Authorization = `Bearer ${id_token}`;
            }

            console.log('✅ Token refresh successful, retrying original request');
            
            // Dispatch token refresh event
            window.dispatchEvent(new CustomEvent('token-refreshed', { detail: updatedUser }));
            
            return axios(originalRequest);
          }
        } catch (refreshError) {
          console.warn('❌ Token refresh failed, falling back to global unauthorized handler:', refreshError);
        }
      }
      
      // If token refresh failed or no refresh token, use global unauthorized handler
      console.log('🔄 Using global unauthorized handler...');
      const handled = globalUnauthorizedHandler(error.response?.status || 401);
      
      if (handled) {
        // Wait a moment for the global handler to potentially refresh the token
        return new Promise((resolve, reject) => {
          setTimeout(() => {
            try {
              // Check if a new token is available after global handler
              const updatedUser = storageService.getUser();
              if (updatedUser) {
                try {
                  // Update auth header with potentially new token
                  if (originalRequest.headers && (updatedUser.id_token || updatedUser.token)) {
                    originalRequest.headers.Authorization = `Bearer ${updatedUser.id_token || updatedUser.token}`;
                  }
                  console.log('🔄 Retrying request with refreshed token from global handler');
                  resolve(axios(originalRequest));
                  return;
                } catch (parseError) {
                  console.error('Failed to parse updated user data:', parseError);
                }
              }
            } catch (storageError) {
              console.error('[API] Failed to get updated user data from encrypted storage:', storageError);
            }
            // If no updated token, reject with original error
            reject(error);
          }, 1000); // Give global handler time to work
        });
      }
    }

    return Promise.reject(error);
  }
);

// Safety check: Reset counter if page is reloaded or user navigates away
window.addEventListener('beforeunload', () => {
  requestCounter = 0;
  updateLoaderState();
});

export default apiClient;
