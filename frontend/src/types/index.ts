// Core type definitions for Zingworks Insight Bot

export interface GoogleUser {
  name: string;
  email: string;
  picture: string;
  access_token: string;
  id_token: string;
  refresh_token: string;
  exp: number; // epoch seconds
  refresh_exp: number; // epoch seconds for refresh token
  token?: string; // Backward compatibility for existing components
  role?: string; // User role for access control
  used_token?: number;
  issued_token?: number;
  report_count?: number;
}

export interface User {
  email: string;
  name: string;
  picture?: string;
  role: 'user' | 'admin';
  isActive: boolean;
  lastLogin?: string;
  access_token?: string;
  id_token?: string;
  refresh_token?: string;
  exp?: number;
  refresh_exp?: number;
  token?: string;
}

export interface AuthContextType {
  user: GoogleUser | null;
  login: (userData: Omit<GoogleUser, 'token'>) => void;
  logout: () => void;
  isLoading?: boolean;
  isAuthenticated?: boolean;
}

export interface SessionContextType {
  sessionId: string | null;
  sessionStatus: 'initializing' | 'creating' | 'active' | 'error';
  sessionError: string;
  hasInputData: boolean;
  updateHasInputData: (hasData: boolean) => void;
  initializeSession: () => Promise<void>;
  cleanupSession: (id?: string | null) => Promise<void>;
  newSession: () => Promise<void>;
  logoutAndCleanup: () => Promise<void>;
  resetSession: () => Promise<void>;
}

export interface SessionData {
  id: string;
  userId: string;
  fileName?: string;
  domainDescription?: string;
  fileDescription?: string;
  businessRules?: string[];
  domainDictionary?: DomainDictionary;
  createdAt: string;
  updatedAt: string;
}

export interface DomainDictionary {
  domain: string;
  data_set_files: Record<string, string>;
  columns: Array<{
    name: string;
    description: string;
    dtype: string;
  }>;
  underlying_conditions_about_dataset: string[];
}

export interface ColumnDescription {
  name: string;
  description: string;
  dataType: string;
  dtype?: string;
  isKey?: boolean;
}

export interface AnalysisJob {
  id: string;
  sessionId: string;
  query: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  progress: number;
  stage: string;
  result?: string;
  htmlReport?: string;
  createdAt: string;
  completedAt?: string;
}

export interface JobProgress {
  stage: string;
  progress: number;
  message: string;
  emoji: string;
  timestamp: string;
}

export interface AdminStats {
  total_users: number;
  total_reports: number;
  total_tokens_used: number;
  active_users: number;
}

export interface FileUploadResponse {
  success: boolean;
  fileName: string;
  size: number;
  columns: string[];
  rowCount: number;
  preview: [];
}

export interface ValidateResponse {
  valid: boolean;
  saved_file?: string;
  errors?: string[] | Record<string, string[]>;
  error?: string;
}

export interface GenerateDomainResponse {
  domain_dictionary: DomainDictionary;
  error?: string;
}

export interface SaveDomainResponse {
  message: string;
  error?: string;
}

export interface CreateJobResponse {
  job_id?: string;
  error?: string;
  status?: string;
  message?: string;
}

export interface Log {
  timestamp: string;
  message: string;
}

export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  message?: string;
  error?: string;
}

export interface SocketEvents {
  job_status: (data: { jobId: string; status: string; progress: number }) => void;
  job_progress: (data: JobProgress) => void;
  job_complete: (data: { jobId: string; result: string; htmlReport: string }) => void;
  job_log: (data: { jobId: string; message: string; timestamp: string }) => void;
  job_error: (data: { jobId: string; error: string }) => void;
}