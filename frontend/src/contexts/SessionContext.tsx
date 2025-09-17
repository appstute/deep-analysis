import React, { createContext, useContext, useEffect, useMemo, useCallback, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { SessionContextType, GoogleUser } from '@/types';
import { storageService } from '@/services/storageService';
import { useAuth } from './AuthContext';
import apiClient from '@/services/apiService';

const SessionContext = createContext<SessionContextType>({
  sessionId: null,
  sessionStatus: 'initializing',
  sessionError: '',
  hasInputData: false,
  updateHasInputData: () => {},
  initializeSession: async () => {},
  cleanupSession: async () => {},
  newSession: async () => {},
  logoutAndCleanup: async () => {},
  resetSession: async () => {},
});

export const useSession = () => {
  const context = useContext(SessionContext);
  if (!context) {
    throw new Error('useSession must be used within a SessionProvider');
  }
  return context;
};

export const SessionProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessionStatus, setSessionStatus] = useState<'initializing' | 'creating' | 'active' | 'error'>('initializing');
  const [sessionError, setSessionError] = useState<string>('');
  const [hasInputData, setHasInputData] = useState<boolean>(false);

  const updateHasInputData = useCallback((hasData: boolean) => {
    setHasInputData(hasData);
    console.log('[SessionContext] Updated hasInputData:', hasData);
  }, []);

  // Initialize session when component mounts or user changes
  useEffect(() => {
    if (user?.token && !sessionId && sessionStatus !== 'creating') {
      void initializeSession();
    }
  }, [user?.token, sessionId, sessionStatus]);

  // Load existing session ID from storage on mount
  useEffect(() => {
    const storedSessionId = storageService.getSessionId();
    if (storedSessionId) {
      setSessionId(storedSessionId);
      setSessionStatus('active');
    }
  }, []);

  const handleUnauthorized = (status: number) => {
    if (status === 401 || status === 403) {
      console.warn('[SessionContext] Unauthorized access, triggering logout');
      void logoutAndCleanup();
      navigate('/unauthorized', { replace: true });
      return true;
    }
    return false;
  };

  const initializeSession = useCallback(async () => {
    if (!user?.token) {
      setSessionError('No user token available');
      setSessionStatus('error');
      return;
    }

    try {
      setSessionStatus('creating');
      setSessionError('');

      // Try stored session first
      const stored = storageService.getSessionId();
      if (stored) {
        interface ValidateResponse {
          valid: boolean;
          session_id: string;
          status: string;
          has_input_data?: boolean;
        }
        const validateResp = await apiClient.get<ValidateResponse>(`/validate_session/${stored}`);
        if (handleUnauthorized(validateResp.status)) return;
        const data = validateResp.data;
        if (data.valid) {
          setSessionId(stored);
          setSessionStatus('active');
          setHasInputData(data.has_input_data || false);
          console.log('[SessionContext] Using existing session:', stored, 'hasInputData:', data.has_input_data);
          return;
        }
        storageService.removeItem('data-analyst-session-id');
      }

      // Create new session using the correct endpoint
      interface CreateResponse {
        session_id: string;
        status: string;
        error?: string;
      }
      const createResp = await apiClient.get<CreateResponse>('/session_id');
      if (handleUnauthorized(createResp.status)) return;
      const created = createResp.data;
      if (created.status === 'success' && created.session_id) {
        setSessionId(created.session_id);
        setSessionStatus('active');
        setHasInputData(false); // New sessions start without input data
        storageService.setSessionId(created.session_id);
        console.log('[SessionContext] Session initialized:', created.session_id);
      } else {
        throw new Error(created.error || 'Failed to create session');
      }
    } catch (error) {
      console.error('[SessionContext] Failed to initialize session:', error);
      setSessionError(error.message || 'Failed to create session');
      setSessionStatus('error');
    }
  }, [user?.token]);

  const cleanupSession = useCallback(async (id?: string | null) => {
    const targetSessionId = id || sessionId;
    if (!targetSessionId) return;

    try {
      await apiClient.post(`/cleanup_session/${targetSessionId}`);
      console.log('[SessionContext] Session cleaned up:', targetSessionId);
    } catch (error) {
      console.warn('[SessionContext] Failed to cleanup session on server:', error);
    }

    // Clear local session data
    storageService.removeItem('data-analyst-session-id');
    setSessionId(null);
    setSessionStatus('initializing');
  }, [sessionId]);

  const newSession = useCallback(async () => {
    // Cleanup existing session first
    if (sessionId) {
      await cleanupSession(sessionId);
    }

    // Create new session
    await initializeSession();
  }, [sessionId, cleanupSession, initializeSession]);

  const logoutAndCleanup = useCallback(async () => {
    try {
      if (sessionId) {
        // Call cleanup API directly without unauthorized handling to avoid redirect loops
        await apiClient.post(`/cleanup_session/${sessionId}`).catch(() => undefined);
      }
    } finally {
      // Remove session id first, then logout and navigate to login
      storageService.removeItem('data-analyst-session-id');
      logout();
      navigate('/login', { replace: true });
    }
  }, [sessionId, logout, navigate]);

  const resetSession = useCallback(async () => {
    if (sessionId) {
      await apiClient.post(`/restart_session/${sessionId}`);
      console.log('[SessionContext] Session reset:', sessionId);
    }
  }, [sessionId]);

  // Cleanup session on page unload
  useEffect(() => {
    const handleBeforeUnload = () => {
      if (sessionId && user?.token) {
        try {
          fetch(`${import.meta.env.VITE_APP_API_URL}/cleanup_session/${sessionId}`, { 
            method: 'POST',
            keepalive: true,
            headers: {
              'Authorization': `Bearer ${user.token}`
            }
          });
        } catch {
          // Best effort cleanup
        }
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
    };
  }, [sessionId, user?.token]);

  const value = useMemo<SessionContextType>(() => ({
    sessionId,
    sessionStatus,
    sessionError,
    hasInputData,
    updateHasInputData,
    initializeSession,
    cleanupSession,
    newSession,
    logoutAndCleanup,
    resetSession,
  }), [sessionId, sessionStatus, sessionError, hasInputData, updateHasInputData, initializeSession, cleanupSession, newSession, logoutAndCleanup, resetSession]);

  return (
    <SessionContext.Provider value={value}>
      {children}
    </SessionContext.Provider>
  );
};
