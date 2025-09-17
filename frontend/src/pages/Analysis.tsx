import React, { useState, useEffect, useRef, useCallback, useLayoutEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { useSession } from '@/contexts/SessionContext';
import '@/styles/scrollbar.css';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Badge } from '@/components/ui/badge';
import { 
  DropdownMenu, 
  DropdownMenuContent, 
  DropdownMenuItem, 
  DropdownMenuSeparator, 
  DropdownMenuTrigger 
} from '@/components/ui/dropdown-menu';
import { Textarea } from '@/components/ui/textarea';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { 
  ArrowUp, 
  Download, 
  Square, 
  Upload,
  LogOut,
  AlertTriangle,
  FileText,
  Plus,
  RotateCcw,
  Loader2,
  Hammer,
  History,
  User,
  ChevronDown
} from 'lucide-react';
import { io, Socket } from 'socket.io-client';
import { Log, CreateJobResponse } from '@/types';
import apiClient from '@/services/apiService';
import { storageService } from '@/services/storageService';

const Analysis: React.FC = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { sessionId, sessionStatus, newSession, logoutAndCleanup, resetSession } = useSession();
  
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState("");
  const [logs, setLogs] = useState<Log[]>([]);
  const [error, setError] = useState('');
  const [jobStatus, setJobStatus] = useState<string>('');
  const [showNewSessionModal, setShowNewSessionModal] = useState(false);
  
  const socketRef = useRef<Socket | null>(null);
  const logSocketRef = useRef<Socket | null>(null);
  const sessionIdRef = useRef<string | null>(null);
  const logContainerRef = useRef<HTMLDivElement>(null);
  const logsEndRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const contentRef = useRef<HTMLDivElement>(null);

  const handleUnauthorized = useCallback((status: number) => {
    if (status === 401 || status === 403) {
      logoutAndCleanup();
      navigate('/unauthorized', { replace: true });
      return true;
    }
    return false;
  }, [logoutAndCleanup, navigate]);

  // Update ref whenever sessionId changes
  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  // Scroll to bottom when logs update
  useLayoutEffect(() => {
    const scrollToBottom = () => {
      // Method 1: Use scrollIntoView on bottom element (most reliable)
      if (logsEndRef.current) {
        logsEndRef.current.scrollIntoView({ 
          behavior: 'smooth', 
          block: 'end' 
        });
        return;
      }

      // Method 2: Find ScrollArea viewport and scroll it
      if (logContainerRef.current) {
        console.log("logContainerRef.current", logContainerRef.current);
        
        // ScrollArea creates a viewport element with this attribute
        const viewport = logContainerRef.current.querySelector('[data-radix-scroll-area-viewport]');
        
        if (viewport) {
          console.log("Found ScrollArea viewport, scrolling...");
          viewport.scrollTop = viewport.scrollHeight;
        } else {
          // Fallback: try direct scroll on the ScrollArea
          console.log("Fallback: trying direct scroll...");
          logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
        }
      }
    };

    // Small delay to ensure DOM is updated
    const timeoutId = setTimeout(scrollToBottom, 100);
    return () => clearTimeout(timeoutId);
  }, [logs]);

  // Cleanup EventSource and WebSocket on unmount
  useEffect(() => {
    return () => {
      if (socketRef.current) {
        socketRef.current.disconnect();
      }
      if (logSocketRef.current) {
        logSocketRef.current.disconnect();
      }
    };
  }, []);

  const setupJobLogSocket = (jobId: string) => {
    // Disconnect any existing log socket
    if (logSocketRef.current) {
      logSocketRef.current.disconnect();
    }
    
    // Connect to API layer WebSocket for dedicated job logs
    const logSocket = io(import.meta.env.VITE_APP_API_URL, {
      transports: ['websocket', 'polling'],
      forceNew: true
    });
    
    logSocketRef.current = logSocket;
    
    logSocket.on('connect', () => {
      console.log('[FRONTEND] Connected to job log WebSocket server');
      // Join the job log monitoring
      logSocket.emit('join_job_logs', { 
        job_id: jobId,
        user_email: user?.email || '',
        session_id: storageService.getSessionId() || ''
      });
    });
    
    logSocket.on('joined_job_logs', (data) => {
      console.log('[FRONTEND] Joined job log streaming:', data.job_id, 'in room:', data.room);
    });
    
    logSocket.on('join_logs_error', (data) => {
      console.error('[FRONTEND] Failed to join job log streaming:', data);
      setError(data.error || 'Failed to join job log streaming');
      logSocket.disconnect();
      logSocketRef.current = null;
    });
    
    logSocket.on('job_log', (logData) => {
      try {
        setLogs(prev => [...prev, logData]);
      } catch (e) {
        console.error('Error handling job log:', e);
      }
    });
    
    logSocket.on('disconnect', () => {
      console.log('[FRONTEND] Disconnected from job log WebSocket server');
    });
    
    logSocket.on('connect_error', (error) => {
      console.error('[FRONTEND] Job log WebSocket connection error:', error);
    });
  };

  const setupJobStatusStream = (jobId: string) => {
    // Disconnect any existing WebSocket connection
    if (socketRef.current) {
      socketRef.current.disconnect();
    }
    
    // Connect to API layer WebSocket
    const socket = io(import.meta.env.VITE_APP_API_URL, {
      transports: ['websocket', 'polling'],
      forceNew: true
    });
    
    socketRef.current = socket;
    
    socket.on('connect', () => {
      console.log('[FRONTEND] Connected to WebSocket server');
      // Join the job monitoring with user email and session ID for privacy
      socket.emit('join_job', { 
        job_id: jobId,
        user_email: user?.email || '',
        session_id: storageService.getSessionId() || ''
      });
    });
    
    socket.on('joined_job', (data) => {
      console.log('[FRONTEND] Joined job-specific monitoring:', data.job_id, 'in room:', data.room);
    });
    
    socket.on('join_error', (data) => {
      console.error('[FRONTEND] Failed to join job monitoring:', data);
      setError(data.error || 'Failed to join job monitoring');
      setLoading(false);
      socket.disconnect();
      socketRef.current = null;
    });
    
    socket.on('job_status', (statusData) => {
      try {
        setJobStatus(statusData.status);
      } catch (e) {
        console.error('Error handling job status:', e);
      }
    });
    
    socket.on('job_progress', (progressData) => {
      try {
        // Add progress message to logs with emoji and details [[memory:6942292]]
        setLogs(prev => [...prev, {
          timestamp: new Date().toLocaleString(),
          message: `${progressData.emoji} ${progressData.stage}: ${progressData.message}`
        }]);
        
        // Update job status to show current stage  
        setJobStatus(`${progressData.stage.toLowerCase().replace(/\s+/g, '_')}`);
        
      } catch (e) {
        console.error('Error handling job progress:', e);
      }
    });
    
    socket.on('job_complete', (statusData) => {
      try {
        setJobStatus(statusData.status);
        
        if (statusData.status === 'completed') {
          // Fetch the completed report
          fetchJobReport(jobId);
        } else if (statusData.status === 'failed') {
          setError(statusData.error || 'Job failed');
          setLoading(false);
        }
        
        // Disconnect the WebSocket
        socket.disconnect();
        socketRef.current = null;
        
        // Also disconnect the log socket when job completes
        if (logSocketRef.current) {
          logSocketRef.current.disconnect();
          logSocketRef.current = null;
        }
        
      } catch (e) {
        console.error('Error handling job completion:', e);
      }
    });
    
    socket.on('job_error', (errorData) => {
      try {
        setError(errorData.error || 'Job monitoring failed');
        setLoading(false);
        socket.disconnect();
        socketRef.current = null;
        
        // Also disconnect the log socket on error
        if (logSocketRef.current) {
          logSocketRef.current.disconnect();
          logSocketRef.current = null;
        }
      } catch (e) {
        console.error('Job error handling failed:', e);
      }
    });
    
    socket.on('disconnect', () => {
      console.log('[FRONTEND] Disconnected from WebSocket server');
    });
    
    socket.on('connect_error', (error) => {
      console.error('[FRONTEND] WebSocket connection error:', error);
      setError('Connection to server failed');
      setLoading(false);
    });
  };

  const fetchJobReport = async (jobId: string) => {
    try {
      const response = await apiClient.get<string>(`/job_report/${jobId}`, { responseType: 'text' });
      setReport(response.data as unknown as string);
      setLoading(false);
    } catch (err) {
      console.error('Error fetching job report:', err);
      setError(err.response?.data?.error || 'Failed to fetch report');
      setLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const currentSessionId = storageService.getSessionId();
    if (!currentSessionId) {
      setError('No active session');
      return;
    }
    setLoading(true);
    setLogs([]);
    setError('');
    setReport('');
    setJobStatus('');

    // Create new AbortController for this request
    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    try {
      // Create job instead of direct analysis
      const resp = await apiClient.post<CreateJobResponse>('/create_job', { 
        query, 
        session_id: currentSessionId 
      }, {
        signal: abortController.signal
      });
      
      if (handleUnauthorized(resp.status)) return;
      const data = resp.data;
      
      if (resp.status === 200 && data.job_id) {
        setJobStatus('pending');
        
        // Start monitoring job status via WebSocket
        setupJobStatusStream(data.job_id);
        
        // Start dedicated job log streaming
        setupJobLogSocket(data.job_id);
        
      } else {
        setError(data.error || 'Job creation failed');
        setLoading(false);
      }
    } catch (err) {
      // Check if the error was caused by the abort
      if (err.name === 'CanceledError' || err.name === 'AbortError') {
        return;
      }
      
      setError(err.response?.data?.error || err.message || 'Error occurred');
      setLoading(false);
    } finally {
      abortControllerRef.current = null;
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // If Enter is pressed without Shift, submit the form
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (!loading && query.trim() && sessionStatus === 'active') {
        handleSubmit(e);
      }
    }
  };

  const handleNewSession = async () => {
    setLogs([]);
    setReport('');
    setError('');
    setQuery('');
    await newSession();
    setShowNewSessionModal(true);
  };

  const handleUploadData = () => {
    navigate('/upload');
  };

  const handleStop = async () => {
    // Abort any ongoing analyze request
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    
    // Disconnect WebSocket
    if (socketRef.current) {
      socketRef.current.disconnect();
      socketRef.current = null;
    }
    
    // Disconnect job log socket
    if (logSocketRef.current) {
      logSocketRef.current.disconnect();
      logSocketRef.current = null;
    }

    // Restart the session to ensure clean state
    await resetSession();

    // Reset UI state including job-related state
    setLoading(false);
    setLogs([]);
    setReport('');
    setError('Analysis stopped by user');
    setJobStatus('');
  };

  const handleDownloadPDF = async () => {
    try {
      const res = await apiClient.post('/generate_pdf', {
        html: report
      }, {
        responseType: 'blob'
      });
      
      // Create a blob link
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", "report.pdf");
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Error downloading PDF:', error);
      setError('Failed to generate PDF');
    }
  };

  return (
    <div className="min-h-screen bg-gradient-dashboard">
      {/* Header */}
      <header className="border-b bg-card/50 backdrop-blur-sm">
        <div className="container mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-4">
              <h1 className="text-xl font-bold">Zingworks Insight Bot</h1>
              <div className="flex items-center space-x-2 text-sm">
                <Badge variant={sessionStatus === 'active' ? 'default' : 'secondary'}>
                  Session: {sessionStatus}
                </Badge>
                {sessionId && (
                  <Badge variant="outline" className="text-xs">
                    ID: {sessionId.substring(0, 8)}...
                  </Badge>
                )}
              </div>
            </div>

            <div className="flex items-center space-x-2">
              <Button
                onClick={handleNewSession}
                disabled={loading || sessionStatus === 'creating'}
                variant="outline"
                size="sm"
              >
                <Plus className="w-4 h-4 mr-2" />
                New Session
              </Button>
              
              <Button
                onClick={handleUploadData}
                variant="outline"
                size="sm"
              >
                <Upload className="w-4 h-4 mr-2" />
                Upload Data
              </Button>

              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" className="flex items-center space-x-3 h-auto p-2">
                    <Avatar className="w-8 h-8">
                      <AvatarImage src={user?.picture} />
                      <AvatarFallback>
                        {user?.name?.charAt(0) || 'U'}
                      </AvatarFallback>
                    </Avatar>
                    <div className="hidden md:block text-left">
                      <p className="text-sm font-medium">{user?.name}</p>
                      <p className="text-xs text-muted-foreground">{user?.email}</p>
                    </div>
                    <ChevronDown className="w-4 h-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-56">
                  {user?.role === 'admin' && (
                    <>
                      <DropdownMenuItem 
                        onClick={() => navigate('/admin')}
                        disabled={loading || sessionStatus === 'creating'}
                      >
                        <Hammer className="w-4 h-4 mr-2" />
                        Admin Dashboard
                      </DropdownMenuItem>
                      <DropdownMenuSeparator />
                    </>
                  )}
                  <DropdownMenuItem onClick={() => navigate('/analysis-history')}>
                    <History className="w-4 h-4 mr-2" />
                    Analysis History
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={logoutAndCleanup}>
                    <LogOut className="w-4 h-4 mr-2" />
                    Sign Out
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <div className="container mx-auto px-6 py-6 h-[calc(100vh-5rem)] flex gap-6">
        {/* Left Panel: Logs + Query */}
        <div className="w-1/3 flex flex-col gap-6 h-full">
          {/* Logs Panel */}
          <Card className="flex-1 flex flex-col min-h-0">
            <CardHeader className="pb-3 pt-4 flex-shrink-0 gap-0 justify-center">
              <CardTitle className="text-lg">Analysis Logs</CardTitle>
              <CardDescription className='!mt-0'>Real-time analysis progress and status updates</CardDescription>
            </CardHeader>
            <CardContent className="flex-1 p-0 min-h-0">
              <ScrollArea className="h-full p-4 pt-0 custom-scrollbar" ref={logContainerRef}>
                <div className="space-y-1">
                  {logs.map((log, i) => (
                    <div key={i} className="text-sm">
                      <div className="text-xs text-muted-foreground mb-1">
                        {log.timestamp}
                      </div>
                      <div className="bg-muted p-2 rounded text-sm log-content">
                        {log.message}
                      </div>
                    </div>
                  ))}
                  {loading && (
                    <div className="flex items-center space-x-2 text-sm text-muted-foreground">
                      <Loader2 className="w-4 h-4 animate-spin" />
                      <span>Processing...</span>
                    </div>
                  )}
                  {/* Invisible element at the bottom for scrolling */}
                  <div ref={logsEndRef} style={{ height: '1px' }} />
                </div>
              </ScrollArea>
            </CardContent>
          </Card>

          {/* Query Panel */}
          <Card className="flex-shrink-0">
            <CardHeader className="pb-0 pt-4">
              <CardTitle className="text-lg">Query Input</CardTitle>
            </CardHeader>
            <CardContent className="p-4">
              <form onSubmit={handleSubmit} className="space-y-3">
                <Textarea 
                  value={query} 
                  onChange={e => setQuery(e.target.value)} 
                  onKeyDown={handleKeyDown}
                  placeholder="Enter your analysis query..." 
                  disabled={loading || sessionStatus !== 'active'} 
                  rows={4}
                  className="resize-none"
                />
                <div className="flex space-x-2">
                  <Button
                    type={loading ? 'button' : 'submit'}
                    onClick={loading ? handleStop : undefined}
                    disabled={loading ? false : (!query.trim() || sessionStatus !== 'active')}
                    className="flex-1"
                  >
                    {loading ? (
                      <>
                        <Square className="w-4 h-4 mr-2" />
                        Stop Analysis
                      </>
                    ) : (
                      <>
                        <ArrowUp className="w-4 h-4 mr-2" />
                        Start Analysis
                      </>
                    )}
                  </Button>
                  
                  {/* {loading && (
                    <Button
                      type="button"
                      onClick={handleStop}
                      variant="outline"
                    >
                      <Square className="w-4 h-4" />
                    </Button>
                  )} */}
                </div>
              </form>
            </CardContent>
          </Card>
        </div>

        {/* Right Panel: Report (Full Height) */}
        <Card className="flex-1 flex flex-col h-full">
          <CardHeader className="pb-3 pt-4 flex-shrink-0">
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-lg">Insight Report</CardTitle>
                <CardDescription>AI-generated analysis results and insights</CardDescription>
              </div>
              {report && (
                <Button onClick={handleDownloadPDF} variant="outline" size="sm">
                  <Download className="w-4 h-4 mr-2" />
                  Download PDF
                </Button>
              )}
            </div>
          </CardHeader>
          <CardContent className="flex-1 p-0 min-h-0">
            <ScrollArea className="h-full p-4 custom-scrollbar">
              {loading ? (
                <div className="flex items-center justify-center h-full">
                  <div className="text-center">
                    <Loader2 className="w-8 h-8 animate-spin mx-auto mb-4" />
                    <p className="text-lg font-medium">⚙️ Running analysis...</p>
                    <p className="text-muted-foreground">Please wait while we process your data</p>
                  </div>
                </div>
              ) : error ? (
                <Alert variant="destructive">
                  <AlertTriangle className="h-4 w-4" />
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              ) : report ? (
                <div ref={contentRef}>
                  <div 
                    className="prose prose-sm max-w-none report-content"
                    dangerouslySetInnerHTML={{ __html: report }} 
                  />
                </div>
              ) : (
                <div className="flex items-center justify-center text-center">
                  <div>
                    <FileText className="w-16 h-16 text-muted-foreground mx-auto mb-4" />
                    <h3 className="text-lg font-medium mb-2">No Analysis Yet</h3>
                    <p className="text-muted-foreground mb-4">
                      Enter a query in the left panel to start your analysis
                    </p>
                  </div>
                </div>
              )}
            </ScrollArea>
          </CardContent>
        </Card>
      </div>

      {/* New Session Modal */}
      {showNewSessionModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <Card className="w-full max-w-md mx-4">
            <CardHeader>
              <CardTitle>New Session Created</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-muted-foreground mb-4">
                A new session has been created successfully. You can now start analyzing data with fresh queries.
              </p>
              <Button onClick={() => setShowNewSessionModal(false)} className="w-full">
                Start Analysis
              </Button>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
};

export default Analysis;
