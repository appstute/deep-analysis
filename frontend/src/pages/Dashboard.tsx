import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { useSession } from '@/contexts/SessionContext';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Badge } from '@/components/ui/badge';
import { 
  Upload, 
  Brain, 
  BarChart3, 
  Settings, 
  FileText, 
  Users,
  LogOut,
  Play,
  PlusCircle
} from 'lucide-react';

const Dashboard: React.FC = () => {
  const { user, logout } = useAuth();
  const { hasInputData } = useSession();
  const navigate = useNavigate();

  const handleGetStarted = () => {
    navigate('/upload');
  };

  const handleContinueAnalysis = () => {
    navigate('/analysis');
  };

  const handleAdminDashboard = () => {
    navigate('/admin');
  };

  return (
    <div className="min-h-screen bg-gradient-dashboard">
      {/* Header */}
      <header className="border-b bg-card/50 backdrop-blur-sm">
        <div className="container mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-4">
              <div className="w-10 h-10 bg-primary rounded-xl flex items-center justify-center">
                <Brain className="w-6 h-6 text-primary-foreground" />
              </div>
              <div>
                <h1 className="text-xl font-bold text-foreground">
                  Zingworks Insight Bot
                </h1>
                <p className="text-sm text-muted-foreground">
                  AI-Powered Data Analysis
                </p>
              </div>
            </div>

            <div className="flex items-center space-x-4">
              <div className="flex items-center space-x-3">
                <Avatar className="w-8 h-8">
                  <AvatarImage src={user?.picture} />
                  <AvatarFallback>
                    {user?.name?.charAt(0) || 'U'}
                  </AvatarFallback>
                </Avatar>
                <div className="hidden md:block">
                  <p className="text-sm font-medium">{user?.name}</p>
                  <div className="flex items-center space-x-2">
                    {/* <Badge variant={user?.role === 'admin' ? 'default' : 'secondary'} className="text-xs">
                      {user?.role}
                    </Badge> */}
                    <p className="text-xs text-muted-foreground">{user?.email}</p>
                  </div>
                </div>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={logout}
                className="flex items-center space-x-2"
              >
                <LogOut className="w-4 h-4" />
                <span className="hidden sm:inline">Sign Out</span>
              </Button>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="container mx-auto px-6 py-12">
        <div className="max-w-4xl mx-auto">
          {/* Welcome Section */}
          <div className="text-center mb-12">
            <h2 className="text-3xl font-bold text-foreground mb-4">
              Welcome back, {user?.name?.split(' ')[0]}! 👋
            </h2>
            <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
              Ready to unlock insights from your data? Upload your dataset and let our AI 
              generate comprehensive analysis reports with domain-specific intelligence.
            </p>
          </div>

          {/* Quick Actions */}
          <div className={`mb-12 gap-6 ${hasInputData ? 'grid md:grid-cols-2' : 'flex justify-center'}`}>
            <Card className={`dashboard-card hover:scale-105 transition-transform cursor-pointer ${!hasInputData ? 'max-w-md' : ''}`} onClick={handleGetStarted}>
              <CardHeader>
                <div className="flex items-center space-x-3">
                  <div className="w-12 h-12 bg-primary/10 rounded-xl flex items-center justify-center">
                    <PlusCircle className="w-6 h-6 text-primary" />
                  </div>
                  <div>
                    <CardTitle className="text-xl">Get Started</CardTitle>
                    <CardDescription>Upload your data and create analysis</CardDescription>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <p className="text-muted-foreground mb-4">
                  Begin with uploading your CSV or Excel file, define your domain context, 
                  and let our AI create a comprehensive analysis.
                </p>
                <div className="flex items-center space-x-4 text-sm text-muted-foreground">
                  <div className="flex items-center space-x-1">
                    <Upload className="w-4 h-4" />
                    <span>Upload Data</span>
                  </div>
                  <div className="flex items-center space-x-1">
                    <Brain className="w-4 h-4" />
                    <span>AI Analysis</span>
                  </div>
                  <div className="flex items-center space-x-1">
                    <FileText className="w-4 h-4" />
                    <span>Get Report</span>
                  </div>
                </div>
              </CardContent>
            </Card>

            {hasInputData && (
              <Card className="dashboard-card hover:scale-105 transition-transform cursor-pointer" onClick={handleContinueAnalysis}>
                <CardHeader>
                  <div className="flex items-center space-x-3">
                    <div className="w-12 h-12 bg-success/10 rounded-xl flex items-center justify-center">
                      <Play className="w-6 h-6 text-success" />
                    </div>
                    <div>
                      <CardTitle className="text-xl">Continue Analysis</CardTitle>
                      <CardDescription>Resume your ongoing data analysis</CardDescription>
                    </div>
                  </div>
                </CardHeader>
                <CardContent>
                  <p className="text-muted-foreground mb-4">
                  Pick up where you left off — use your last session's data to generate a new report.
                  </p>
                  <div className="flex items-center space-x-4 text-sm text-muted-foreground">
                    <div className="flex items-center space-x-1">
                      <BarChart3 className="w-4 h-4" />
                      <span>Live logs</span>
                    </div>
                    <div className="flex items-center space-x-1">
                      <Brain className="w-4 h-4" />
                      <span>AI analysis</span>
                    </div>
                    <div className="flex items-center space-x-1">
                      <FileText className="w-4 h-4" />
                      <span>Export PDF</span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}
          </div>

          {/* Admin Section */}
          {user?.role === 'admin' && (
            <div className="mb-8">
              <h3 className="text-xl font-semibold text-foreground mb-4">Admin Tools</h3>
              <Card className="dashboard-card hover:scale-105 transition-transform cursor-pointer" onClick={handleAdminDashboard}>
                <CardHeader>
                  <div className="flex items-center space-x-3">
                    <div className="w-12 h-12 bg-warning/10 rounded-xl flex items-center justify-center">
                      <Users className="w-6 h-6 text-warning" />
                    </div>
                    <div>
                      <CardTitle className="text-xl">Admin Dashboard</CardTitle>
                      <CardDescription>Manage users and Tokens</CardDescription>
                    </div>
                  </div>
                </CardHeader>
                {/* <CardContent>
                  <p className="text-muted-foreground mb-4">
                    Access user management tools, view system statistics, and monitor 
                    platform usage and performance metrics.
                  </p>
                  <div className="flex items-center space-x-4 text-sm text-muted-foreground">
                    <div className="flex items-center space-x-1">
                      <Users className="w-4 h-4" />
                      <span>User Management</span>
                    </div>
                    <div className="flex items-center space-x-1">
                      <BarChart3 className="w-4 h-4" />
                      <span>Analytics</span>
                    </div>
                    <div className="flex items-center space-x-1">
                      <Settings className="w-4 h-4" />
                      <span>System Settings</span>
                    </div>
                  </div>
                </CardContent> */}
              </Card>
            </div>
          )}

          {/* Recent Activity Placeholder */}
          {/* <div className="text-center py-12 border-2 border-dashed border-border rounded-xl">
            <BarChart3 className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
            <h3 className="text-lg font-medium text-foreground mb-2">
              Your Analysis History
            </h3>
            <p className="text-muted-foreground mb-6">
              Your recent analysis sessions and reports will appear here
            </p>
            <Button variant="outline" onClick={handleGetStarted}>
              <PlusCircle className="w-4 h-4 mr-2" />
              Create Your First Analysis
            </Button>
          </div> */}
        </div>
      </main>
    </div>
  );
};

export default Dashboard;