import apiClient from './apiService';

export interface User {
  email: string;
  name: string;
  role: string;
  used_token: number;
  issued_token: number;
  report_count: number;
  created_at?: string;
  updated_at?: string;
  is_active?: boolean;
  status?: 'active' | 'inactive' | 'suspended';
  last_login?: string;
  picture?: string;
}

export interface CreateUserRequest {
  email: string;
  name: string;
  role: string;
  issued_token: number;
}

export interface UpdateUserRequest {
  name?: string;
  role?: string;
  issued_token?: number;
  used_token?: number;
  is_active?: boolean;
}

export interface TokenHistoryRecord {
  history_id: string;
  user_email: string;
  tokens_added: number;
  previous_tokens: number;
  new_total_tokens: number;
  added_by: string;
  reason?: string;
  created_at: string;
}

export interface AdminStats {
  total_users: number;
  total_reports: number;
  total_tokens_used: number;
  active_users: number;
}

class UserService {
  private baseUrl = '/api/users';

  // Get all users (admin only)
  async getAllUsers(): Promise<User[]> {
    try {
      const response = await apiClient.get(`${this.baseUrl}`);
      return response.data.users || [];
    } catch (error) {
      console.error('Failed to fetch users:', error);
      throw error;
    }
  }

  // Get user by email
  async getUserByEmail(email: string): Promise<User | null> {
    try {
      const response = await apiClient.get(`${this.baseUrl}/${encodeURIComponent(email)}`);
      return response.data.user;
    } catch (error) {
      console.error(`Failed to fetch user ${email}:`, error);
      return null;
    }
  }

  // Create new user (admin only)
  async createUser(userData: CreateUserRequest): Promise<boolean> {
    try {
      const response = await apiClient.post(`${this.baseUrl}`, {
        ...userData,
        used_token: 0,
        report_count: 0
      });
      return response.data.success || false;
    } catch (error) {
      console.error('Failed to create user:', error);
      throw error;
    }
  }

  // Update user (admin only)
  async updateUser(email: string, updateData: UpdateUserRequest): Promise<boolean> {
    try {
      const response = await apiClient.put(`${this.baseUrl}/${encodeURIComponent(email)}`, updateData);
      return response.data.success || false;
    } catch (error) {
      console.error(`Failed to update user ${email}:`, error);
      throw error;
    }
  }

  // Delete user (admin only)
  async deleteUser(email: string): Promise<boolean> {
    try {
      const response = await apiClient.delete(`${this.baseUrl}/${encodeURIComponent(email)}`);
      return response.data.success || false;
    } catch (error) {
      console.error(`Failed to delete user ${email}:`, error);
      throw error;
    }
  }

  // Get current user's profile and role
  async getCurrentUserProfile(): Promise<User | null> {
    try {
      const response = await apiClient.get('/api/profile');
      return response.data.user;
    } catch (error) {
      console.error('Failed to fetch current user profile:', error);
      return null;
    }
  }

  // Update current user's token usage
  async updateTokenUsage(email: string, tokensUsed: number): Promise<boolean> {
    try {
      const response = await apiClient.post('/api/tokens/update', {
        email,
        tokens_used: tokensUsed
      });
      return response.data.success || false;
    } catch (error) {
      console.error('Failed to update token usage:', error);
      return false;
    }
  }

  // Add tokens to user's existing allocation (admin only)
  async addTokensToUser(email: string, tokensToAdd: number, reason?: string): Promise<{
    success: boolean;
    previous_tokens?: number;
    new_total?: number;
    message?: string;
    history_created?: boolean;
  }> {
    try {
      const response = await apiClient.post(`${this.baseUrl}/${encodeURIComponent(email)}/add-tokens`, {
        tokens_to_add: tokensToAdd,
        reason: reason || ''
      });
      return {
        success: response.data.success || false,
        previous_tokens: response.data.previous_tokens,
        new_total: response.data.new_total,
        message: response.data.message,
        history_created: response.data.history_created
      };
    } catch (error) {
      console.error(`Failed to add tokens to user ${email}:`, error);
      throw error;
    }
  }

  // Get token history for a user (admin only)
  async getUserTokenHistory(email: string, limit: number = 50): Promise<TokenHistoryRecord[]> {
    try {
      const response = await apiClient.get(`${this.baseUrl}/${encodeURIComponent(email)}/token-history`, {
        params: { limit }
      });
      return response.data.history || [];
    } catch (error) {
      console.error(`Failed to fetch token history for user ${email}:`, error);
      throw error;
    }
  }

  // Get user statistics (admin only)
  async getUserStats(): Promise<AdminStats> {
    try {
      const response = await apiClient.get('/api/admin/stats');
      return response.data.stats;
    } catch (error) {
      console.error('Failed to fetch user stats:', error);
      return {
        total_users: 0,
        total_reports: 0,
        total_tokens_used: 0,
        active_users: 0
      };
    }
  }

  // Toggle user status (admin only) - Uses correct backend endpoint
  async toggleUserStatus(email: string, isActive: boolean): Promise<boolean> {
    try {
      const status = isActive ? 'active' : 'inactive';
      const response = await apiClient.put(`/users/${encodeURIComponent(email)}/status`, {
        status: status
      });
      return response.status === 200;
    } catch (error) {
      console.error(`Failed to toggle user status for ${email}:`, error);
      throw error;
    }
  }

  // Change user role (admin only) - Uses correct backend endpoint
  async changeUserRole(email: string, newRole: 'user' | 'admin'): Promise<boolean> {
    try {
      const response = await apiClient.put(`/users/${encodeURIComponent(email)}/role`, {
        role: newRole
      });
      return response.status === 200;
    } catch (error) {
      console.error(`Failed to change user role for ${email}:`, error);
      throw error;
    }
  }

  // Get users for admin dashboard (admin only) - Uses correct backend endpoint
  async getAdminUsers(): Promise<User[]> {
    try {
      const response = await apiClient.get('/api/users');
      return response.data.users || [];
    } catch (error) {
      console.error('Failed to fetch admin users:', error);
      throw error;
    }
  }

  // Get admin statistics (admin only) - Uses correct backend endpoint
  async getAdminStats(): Promise<AdminStats> {
    try {
      const response = await apiClient.get('/api/admin/stats');
      return response.data.stats;
    } catch (error) {
      console.error('Failed to fetch admin stats:', error);
      return {
        total_users: 0,
        total_reports: 0,
        total_tokens_used: 0,
        active_users: 0
      };
    }
  }
}

export default new UserService();
