import axios from 'axios';
import { ApiResponse, User } from '@/types';

const API_URL = import.meta.env.VITE_APP_API_URL || 'http://localhost:8000';

class AuthService {
  async googleAuth(googleToken: string): Promise<ApiResponse<{ user: User; token: string }>> {
    try {
      const response = await axios.post(`${API_URL}/google_auth`, {
        token: googleToken,
      });
      return response.data;
    } catch (error) {
      console.error('Google auth error:', error);
      return {
        success: false,
        error: error.response?.data?.message || 'Authentication failed',
      };
    }
  }

  async refreshToken(token: string): Promise<ApiResponse<{ user: User; token: string }>> {
    try {
      const response = await axios.post(`${API_URL}/refresh_token`, {}, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });
      return response.data;
    } catch (error) {
      console.error('Token refresh error:', error);
      return {
        success: false,
        error: error.response?.data?.message || 'Token refresh failed',
      };
    }
  }

  async verifyToken(token: string): Promise<boolean> {
    try {
      const response = await axios.get(`${API_URL}/verify_token`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });
      return response.data.success;
    } catch (error) {
      return false;
    }
  }
}

export const authService = new AuthService();