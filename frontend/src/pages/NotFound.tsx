import { useLocation } from "react-router-dom";
import { useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { AlertTriangle, ArrowLeft, Home } from "lucide-react";

const NotFound = () => {
  const location = useLocation();

  useEffect(() => {
    console.error(
      "404 Error: User attempted to access non-existent route:",
      location.pathname
    );
  }, [location.pathname]);

  return (
    <div className="min-h-screen bg-gradient-dashboard flex items-center justify-center p-4">
      <Card className="w-full max-w-md shadow-[var(--shadow-elevated)]">
        <CardHeader className="text-center">
          <div className="w-16 h-16 bg-destructive/10 rounded-2xl flex items-center justify-center mx-auto mb-4">
            <AlertTriangle className="w-8 h-8 text-destructive" />
          </div>
          <CardTitle className="text-2xl">Page Not Found</CardTitle>
          <CardDescription>
            The page you're looking for doesn't exist
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-center text-muted-foreground">
            The URL "{location.pathname}" could not be found on this server. 
            Please check the URL and try again.
          </p>
          
          <div className="flex flex-col sm:flex-row gap-2">
            <Button
              variant="outline"
              onClick={() => window.history.back()}
              className="flex items-center justify-center"
            >
              <ArrowLeft className="w-4 h-4 mr-2" />
              Go Back
            </Button>
            <Button
              onClick={() => window.location.href = '/'}
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

export default NotFound;
