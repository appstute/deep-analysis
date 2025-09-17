import CryptoJS from 'crypto-js';
import { GoogleUser } from '@/types';

// Simple encryption key - In production, this should come from environment variables
const ENCRYPTION_KEY = import.meta.env.VITE_APP_ENCRYPTION_KEY || 'data-analyst-crypto-key-2024';

/**
 * Simple crypto storage utility for encrypting/decrypting localStorage data
 * Uses AES encryption with crypto-js
 */
export class StorageService {
  private static instance: StorageService;

  private constructor() {}

  public static getInstance(): StorageService {
    if (!StorageService.instance) {
      StorageService.instance = new StorageService();
    }
    return StorageService.instance;
  }

  /**
   * Encrypt data before storing
   */
  private encrypt(text: string): string {
    try {
      const encrypted = CryptoJS.AES.encrypt(text, ENCRYPTION_KEY).toString();
      return encrypted;
    } catch (error) {
      console.error('[StorageService] Encryption failed:', error);
      throw error;
    }
  }

  /**
   * Decrypt data after retrieving
   */
  private decrypt(encryptedText: string): string {
    try {
      const bytes = CryptoJS.AES.decrypt(encryptedText, ENCRYPTION_KEY);
      const decrypted = bytes.toString(CryptoJS.enc.Utf8);
      
      if (!decrypted) {
        throw new Error('Failed to decrypt data - invalid key or corrupted data');
      }
      
      return decrypted;
    } catch (error) {
      console.error('[StorageService] Decryption failed:', error);
      throw error;
    }
  }

  /**
   * Store encrypted data in localStorage
   */
  public setItem(key: string, value: string): void {
    try {
      const encryptedValue = this.encrypt(value);
      localStorage.setItem(key, encryptedValue);
      
      console.log(`[StorageService] Data stored with encryption for key: ${key}`);
    } catch (error) {
      console.error(`[StorageService] Failed to store encrypted data for key ${key}:`, error);
      throw error;
    }
  }

  /**
   * Retrieve and decrypt data from localStorage
   */
  public getItem(key: string): string | null {
    try {
      const encryptedValue = localStorage.getItem(key);
      
      if (!encryptedValue) {
        return null;
      }

      // Try to decrypt the value - if it fails, it might be plain text
      try {
        const decryptedValue = this.decrypt(encryptedValue);
        return decryptedValue;
      } catch (decryptError) {
        // If decryption fails, assume it's plain text and migrate it
        console.warn(`[StorageService] Found plain text data for key ${key}, migrating to encrypted storage`);
        this.setItem(key, encryptedValue);
        return encryptedValue;
      }
    } catch (error) {
      console.error(`[StorageService] Failed to retrieve data for key ${key}:`, error);
      return null;
    }
  }

  /**
   * Remove data from localStorage
   */
  public removeItem(key: string): void {
    try {
      localStorage.removeItem(key);
      console.log(`[StorageService] Removed data for key: ${key}`);
    } catch (error) {
      console.error(`[StorageService] Failed to remove data for key ${key}:`, error);
    }
  }

  // Legacy methods for compatibility
  setToken(token: string): void {
    this.setItem('google-user-token', token);
  }

  getToken(): string | null {
    // Try to get from user object first
    const user = this.getUser();
    if (user?.id_token) return user.id_token;
    if (user?.access_token) return user.access_token;
    if (user?.token) return user.token;
    
    // Fallback to direct token storage
    return this.getItem('google-user-token');
  }

  setUser(user: GoogleUser): void {
    console.log('[StorageService] Storing user data:', {
      email: user.email,
      role: user.role,
      hasRole: !!user.role
    });
    this.setItem('google-user', JSON.stringify(user));
  }

  getUser(): GoogleUser | null {
    try {
      const stored = this.getItem('google-user');
      if (!stored) return null;
      
      const parsed = JSON.parse(stored);
      console.log('[StorageService] Retrieved user data:', {
        email: parsed.email,
        role: parsed.role,
        hasRole: !!parsed.role
      });
      return parsed;
    } catch (error) {
      console.error('Error parsing user data:', error);
      this.clearAuth();
      return null;
    }
  }

  setSessionId(sessionId: string): void {
    this.setItem('data-analyst-session-id', sessionId);
  }

  getSessionId(): string | null {
    return this.getItem('data-analyst-session-id');
  }

  setSessionData(sessionId: string, data: any): void {
    this.setItem(`session_${sessionId}`, JSON.stringify(data));
  }

  getSessionData(sessionId: string): any | null {
    try {
      const stored = this.getItem(`session_${sessionId}`);
      if (!stored) return null;
      return JSON.parse(stored);
    } catch (error) {
      console.error('Error parsing session data:', error);
      return null;
    }
  }

  clearAuth(): void {
    this.removeItem('google-user');
    this.removeItem('google-user-token');
    this.removeItem('data-analyst-session-id');
    
    // Clear all session data
    const keys = Object.keys(localStorage);
    keys.forEach(key => {
      if (key.startsWith('session_')) {
        localStorage.removeItem(key);
      }
    });
  }

  clearSessionData(sessionId: string): void {
    this.removeItem(`session_${sessionId}`);
  }

  /**
   * Check if data exists for a key
   */
  public hasItem(key: string): boolean {
    return localStorage.getItem(key) !== null;
  }

  /**
   * Clear specific encrypted data from localStorage
   */
  public clear(): void {
    try {
      // Remove known encrypted keys
      this.removeItem('google-user');
      this.removeItem('data-analyst-session-id');
      
      console.log(`[StorageService] Cleared encrypted items from localStorage`);
    } catch (error) {
      console.error('[StorageService] Failed to clear encrypted data:', error);
    }
  }
}

// Export singleton instance
export const storageService = StorageService.getInstance();