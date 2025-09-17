import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { AlertTriangle, ArrowLeft, Home } from 'lucide-react';

const Unauthorized: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-gradient-dashboard flex items-center justify-center p-4">
      <Card className="w-full max-w-md shadow-[var(--shadow-elevated)]">
        <CardHeader className="text-center">
          <div className="w-16 h-16 bg-warning/10 rounded-2xl flex items-center justify-center mx-auto mb-4">
            <AlertTriangle className="w-8 h-8 text-warning" />
          </div>
          <CardTitle className="text-2xl">Access Denied</CardTitle>
          <CardDescription>
            You don't have permission to access this resource
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-center text-muted-foreground">
            This page requires administrator privileges. Please contact your system 
            administrator if you believe this is an error.
          </p>
          
          <div className="flex flex-col sm:flex-row gap-2">
            <Button
              variant="outline"
              onClick={() => navigate(-1)}
              className="flex items-center justify-center"
            >
              <ArrowLeft className="w-4 h-4 mr-2" />
              Go Back
            </Button>
            <Button
              onClick={() => navigate('/')}
              className="flex items-center justify-center"
            >
              <Home className="w-4 h-4 mr-2" />
              Dashboard
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default Unauthorized;