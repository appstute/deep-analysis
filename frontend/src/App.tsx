import React, { useEffect, useState } from 'react';
import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { GoogleOAuthProvider } from '@react-oauth/google';
import { AuthProvider } from "@/contexts/AuthContext";
import { SessionProvider } from "@/contexts/SessionContext";
import { LoaderProvider } from "@/contexts/LoaderContext";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import GlobalLoader from "@/components/GlobalLoader";
import Dashboard from "./pages/Dashboard";
import Login from "./pages/Login";
import Unauthorized from "./pages/Unauthorized";
import NotFound from "./pages/NotFound";
import Upload from "./pages/Upload";
import AnalysisHistory from './pages/AnalysisHistory';
import AdminDashboard from './pages/AdminDashboard';
import Analysis from './pages/Analysis';
import SalesforceConnector from './pages/SalesforceConnector';

const queryClient = new QueryClient();

const App: React.FC = () => {
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    const handleLoaderState = (event: Event) => {
      const customEvent = event as CustomEvent;
      setIsLoading(customEvent.detail.isLoading);
    };

    window.addEventListener('api-loader-state-change', handleLoaderState);

    return () => {
      window.removeEventListener('api-loader-state-change', handleLoaderState);
    };
  }, []);

  return (
    <GoogleOAuthProvider clientId={import.meta.env.VITE_APP_GOOGLE_CLIENT_ID || ''}>
      <QueryClientProvider client={queryClient}>
        <TooltipProvider>
          <Toaster />
          <Sonner />
          <BrowserRouter>
            <LoaderProvider>
              <AuthProvider>
                <SessionProvider>
                  <GlobalLoader isLoading={isLoading} />
                  <Routes>
                  <Route path="/login" element={<Login />} />
                  <Route path="/unauthorized" element={<Unauthorized />} />
                  <Route 
                    path="/" 
                    element={
                      <ProtectedRoute>
                        <Dashboard />
                      </ProtectedRoute>
                    } 
                  />
                  <Route 
                    path="/upload" 
                    element={
                      <ProtectedRoute>
                        <Upload />
                      </ProtectedRoute>
                    } 
                  />
                  <Route 
                    path="/analysis" 
                    element={
                      <ProtectedRoute>
                        <Analysis />
                      </ProtectedRoute>
                    } 
                  />
                  <Route 
                    path="/connect/salesforce" 
                    element={
                      <ProtectedRoute>
                        <SalesforceConnector />
                      </ProtectedRoute>
                    } 
                  />
                  <Route 
                    path="/analysis-history" 
                    element={
                      <ProtectedRoute>
                        <AnalysisHistory />
                      </ProtectedRoute>
                    } 
                  />
                  <Route 
                    path="/admin" 
                    element={
                      <ProtectedRoute requireAdmin>
                        <AdminDashboard />
                      </ProtectedRoute>
                    } 
                  />
                  <Route 
                    path="/connect/salesforce" 
                    element={
                      <ProtectedRoute requireAdmin>
                        <SalesforceConnector />
                      </ProtectedRoute>
                    } 
                  />
                  <Route path="*" element={<NotFound />} />
                </Routes>
              </SessionProvider>
            </AuthProvider>
          </LoaderProvider>
          </BrowserRouter>
        </TooltipProvider>
      </QueryClientProvider>
    </GoogleOAuthProvider>
  );
};

export default App;
