import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { Loader2 } from 'lucide-react';

interface ProtectedRouteProps {
  children: React.ReactNode;
  requireAdmin?: boolean;
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ 
  children, 
  requireAdmin = false 
}) => {
  const { user } = useAuth();
  const location = useLocation();

  // If no user, redirect to login
  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  // If admin required but user is not admin, redirect to unauthorized
  if (requireAdmin && user?.role !== 'admin') {
    return <Navigate to="/unauthorized" replace />;
  }

  return <>{children}</>;
};