import React, { useState } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { useGoogleLogin, CodeResponse } from '@react-oauth/google';
import { useAuth } from '@/contexts/AuthContext';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { AlertCircle, BarChart3, Brain, Database, Loader2 } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import GoogleButton from '@/components/GoogleButton';
import apiClient from '@/services/apiService';
import { storageService } from '@/services/storageService';

interface AuthResponse {
  access_token: string;
  id_token: string;
  refresh_token: string;
  expires_in: number;
}

interface TokenInfo {
  email: string;
  name: string;
  picture: string;
  exp: number;
}

const Login: React.FC = () => {
  const { login, user } = useAuth();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const location = useLocation();

  const from = location.state?.from?.pathname || '/';

  const checkEmailAuthorization = async (email: string) => {
    try {
      const response = await apiClient.get(`/users/${encodeURIComponent(email)}`);
      return {authorized: response.status === 200 && response.data, role: response.data.role};
    } catch (error) {
      return {authorized: false, role: ''};
    }
  };

  const googleLogin = useGoogleLogin({
    flow: 'auth-code',
    onSuccess: async (codeResponse: CodeResponse) => {
      if (codeResponse.code) {
        setLoading(true);
        setError(null);
        try {
          // Exchange code for tokens
          const response = await apiClient.post<AuthResponse>('/google_auth', {
            code: codeResponse.code
          });

          // Get token info from Google
          const tokenInfo = await apiClient.get<TokenInfo>(
            `https://oauth2.googleapis.com/tokeninfo?id_token=${response.data.id_token}`
          );

          // Check if email is authorized
          const userData = await checkEmailAuthorization(tokenInfo.data.email);
          if (!userData.authorized.authorized) {
            navigate('/unauthorized', { replace: true });
            return;
          }
          
          const now = Math.floor(Date.now() / 1000);
          
          login({
            role: userData.role,
            name: tokenInfo.data.name,
            email: tokenInfo.data.email,
            picture: tokenInfo.data.picture,
            access_token: response.data.access_token,
            id_token: response.data.id_token,
            refresh_token: response.data.refresh_token,
            exp: tokenInfo.data.exp,
            refresh_exp: now + (3600 * 24 * 7) // 7 days
          });

          // Verify that data was stored in localStorage
          const storedUser = storageService.getUser();
          if (!storedUser) {
            throw new Error('Failed to store user data');
          }

          // Navigate to the main page after successful login
          navigate('/', { replace: true });
        } catch (err) {
          console.error('Login failed:', err);
          setError(err instanceof Error ? err.message : 'Login failed. Please try again.');
        } finally {
          setLoading(false);
        }
      }
    },
    onError: (errorResponse: Pick<CodeResponse, "error" | "error_description" | "error_uri">) => {
      console.error('Google Login Failed:', errorResponse.error_description || errorResponse.error);
      setError('Google login failed. Please try again.');
      setLoading(false);
    }
  });

  if (user) {
    return <Navigate to={from} replace />;
  }

  return (
    <div className="min-h-screen bg-gradient-dashboard flex items-center justify-center p-4">
      <div className="w-full max-w-md space-y-8">
        {/* Logo and Header */}
        <div className="text-center">
          <div className="flex items-center justify-center mb-6">
            <div className="w-16 h-16 bg-primary rounded-2xl flex items-center justify-center shadow-[var(--shadow-elevated)]">
              <Brain className="w-8 h-8 text-primary-foreground" />
            </div>
          </div>
          <h1 className="text-3xl font-bold text-foreground mb-2">
            Zingworks Insight Bot
          </h1>
          <p className="text-muted-foreground">
            AI-Powered Data Analysis Platform
          </p>
        </div>

        {/* Features Preview */}
        <div className="grid grid-cols-3 gap-4 mb-8">
          <div className="text-center p-4 bg-card rounded-xl border shadow-sm">
            <Database className="w-6 h-6 text-primary mx-auto mb-2" />
            <p className="text-xs text-muted-foreground">Upload Data</p>
          </div>
          <div className="text-center p-4 bg-card rounded-xl border shadow-sm">
            <Brain className="w-6 h-6 text-primary mx-auto mb-2" />
            <p className="text-xs text-muted-foreground">AI Analysis</p>
          </div>
          <div className="text-center p-4 bg-card rounded-xl border shadow-sm">
            <BarChart3 className="w-6 h-6 text-primary mx-auto mb-2" />
            <p className="text-xs text-muted-foreground">Get Insights</p>
          </div>
        </div>

        {/* Login Card */}
        <Card className="shadow-[var(--shadow-elevated)]">
          <CardHeader className="text-center">
            <CardTitle>Sign In to Continue</CardTitle>
            <CardDescription>
              Use your Google account to access the platform
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {error && (
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            <GoogleButton
              onClick={() => googleLogin()}
              disabled={loading}
              loading={loading}
            />

            <p className="text-xs text-muted-foreground text-center">
              By signing in, you agree to our Terms of Service and Privacy Policy
            </p>
          </CardContent>
        </Card>

        {/* Footer */}
        <p className="text-center text-sm text-muted-foreground">
          Secure authentication powered by Google OAuth 2.0
        </p>
      </div>
    </div>
  );
};

export default Login;