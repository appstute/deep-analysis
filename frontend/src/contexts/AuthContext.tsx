import React, { createContext, useState, useEffect, ReactNode, useContext } from 'react';
import { GoogleUser, AuthContextType } from '@/types';
import { storageService } from '@/services/storageService';

const AuthContext = createContext<AuthContextType>({
  user: null,
  login: () => {},
  logout: () => {},
});

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const [user, setUser] = useState<GoogleUser | null>(() => {
    try {
      const stored = storageService.getUser();
      if (!stored) {
        console.log('[AuthContext] No user data found in storage');
        return null;
      }
      console.log('[AuthContext] User data loaded from storage:', {
        email: stored.email,
        role: stored.role,
        hasRole: !!stored.role
      });
      return stored as GoogleUser;
    } catch (error) {
      console.error('[AuthContext] Failed to load user data from storage:', error);
      return null;
    }
  });

  // Persist user changes to localStorage
  useEffect(() => {
    if (user) {
      try {
        storageService.setUser(user);
        console.log('[AuthContext] User data persisted to localStorage:', {
          email: user.email,
          role: user.role,
          hasRole: !!user.role
        });
      } catch (error) {
        console.error('[AuthContext] Failed to persist user data to localStorage:', error);
      }
    }
  }, [user]);

  // Verify role persistence after user state changes
  useEffect(() => {
    if (user) {
      // Small delay to ensure localStorage write is complete
      setTimeout(() => {
        const storedUser = storageService.getUser();
        if (storedUser && storedUser.role !== user.role) {
          console.warn('[AuthContext] Role mismatch detected! Current:', user.role, 'Stored:', storedUser.role);
        } else if (storedUser) {
          console.log('[AuthContext] Role persistence verified:', storedUser.role);
        }
      }, 100);
    }
  }, [user?.role]);

  // Listen for token refresh events from api client
  useEffect(() => {
    const tokenRefreshHandler = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (!detail) return;
      try {
        const next = {
          name: detail.name || user?.name,
          email: detail.email || user?.email,
          picture: detail.picture || user?.picture,
          role: detail.role || user?.role, // Preserve role from existing user data
          access_token: detail.access_token || detail.token,
          id_token: detail.id_token || detail.token,
          refresh_token: detail.refresh_token || user?.refresh_token,
          exp: detail.exp,
          refresh_exp: detail.refresh_exp || user?.refresh_exp,
          token: detail.access_token || detail.token, // For backward compatibility
        } as GoogleUser;
        setUser(next);
        console.log('[AuthContext] User token refreshed with role preserved');
      } catch (error) {
        console.error('[AuthContext] Failed to process token refresh:', error);
      }
    };

    // Listen for force logout events from global unauthorized handler
    const forceLogoutHandler = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      console.warn('[AuthContext] Force logout triggered:', detail?.reason || 'Unknown reason');
      setUser(null);
      storageService.clearAuth();
    };

    // Listen for auth success events (optional - for logging)
    const authSuccessHandler = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      console.log('[AuthContext] Auth success:', detail?.message || 'Authentication successful');
    };

    // Listen for auth error events (optional - for logging)
    const authErrorHandler = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      console.warn('[AuthContext] Auth error:', detail?.message || 'Authentication error');
    };

    window.addEventListener('token-refreshed', tokenRefreshHandler as EventListener);
    window.addEventListener('force-logout', forceLogoutHandler as EventListener);
    window.addEventListener('auth-success', authSuccessHandler as EventListener);
    window.addEventListener('auth-error', authErrorHandler as EventListener);

    return () => {
      window.removeEventListener('token-refreshed', tokenRefreshHandler as EventListener);
      window.removeEventListener('force-logout', forceLogoutHandler as EventListener);
      window.removeEventListener('auth-success', authSuccessHandler as EventListener);
      window.removeEventListener('auth-error', authErrorHandler as EventListener);
    };
  }, [user]);

  const login = (userData: Omit<GoogleUser, 'token'>) => {
    try {
      const user: GoogleUser = {
        ...userData,
        token: userData.access_token, // For backward compatibility
      };
      
      console.log('[AuthContext] Logging in user with data:', {
        email: user.email,
        role: user.role,
        hasRole: !!user.role
      });
      
      setUser(user);
      
      // Immediately persist to localStorage
      try {
        storageService.setUser(user);
        console.log('[AuthContext] User data persisted to localStorage on login');
      } catch (storageError) {
        console.error('[AuthContext] Failed to persist user data to localStorage on login:', storageError);
      }
    } catch (err) {
      console.error('[AuthContext] Failed to set user data:', err);
    }
  };

  // Manual logout function (only called when user clicks sign out)
  const logout = () => {
    setUser(null);
    storageService.clearAuth();
    window.location.reload();
  };

  return (
    <AuthContext.Provider value={{ user, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
};