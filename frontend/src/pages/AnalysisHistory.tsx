import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { Input } from '@/components/ui/input';
import { 
  DropdownMenu, 
  DropdownMenuContent, 
  DropdownMenuItem, 
  DropdownMenuSeparator, 
  DropdownMenuTrigger 
} from '@/components/ui/dropdown-menu';
import { 
  ArrowLeft,
  Calendar,
  Download,
  FileText,
  LogOut,
  ChevronDown,
  Hammer,
  History,
  Search,
  Loader2,
  RotateCcw,
  X
} from 'lucide-react';
import { useSession } from '@/contexts/SessionContext';
import apiClient from '@/services/apiService';

// Interface for analysis history item
interface AnalysisHistoryItem {
  id: string;
  query: string;
  timestamp: string;
  status: 'completed' | 'failed' | 'running';
  reportUrl: string;
  sessionId: string;
  totalTokens: number;
  totalCost: number;
}

// Interface for raw API response item (before validation)
interface RawHistoryItem {
  id?: string;
  query?: string;
  timestamp?: string;
  status?: string;
  reportUrl?: string;
  sessionId?: string;
  totalTokens?: number | string;
  totalCost?: number | string;
}

const AnalysisHistory: React.FC = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { logoutAndCleanup } = useSession();
  const [selectedHistory, setSelectedHistory] = useState<AnalysisHistoryItem | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [historyData, setHistoryData] = useState<AnalysisHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedReportHtml, setSelectedReportHtml] = useState<string>('');

  // Filter history data based on search query (memoized for performance)
  const filteredHistoryData = useMemo(() => 
    historyData.filter(item =>
      (item.query || '').toLowerCase().includes(searchQuery.toLowerCase())
    ), [historyData, searchQuery]
  );

  // Fetch analysis history on component mount
  useEffect(() => {
    fetchAnalysisHistory();
  }, []);

  const fetchAnalysisHistory = async () => {
    try {
      setLoading(true);
      setError('');
      
      const response = await apiClient.get('/analysis_history');
      const data = response.data;
      
      if (data.history && Array.isArray(data.history)) {
        // Validate and sanitize each item
        const validatedItems = data.history.map((item: RawHistoryItem) => ({
          id: item.id || '',
          query: item.query || 'Unnamed Analysis',
          timestamp: item.timestamp || new Date().toISOString(),
          status: (item.status && ['completed', 'failed', 'running'].includes(item.status)) ? item.status : 'unknown',
          reportUrl: item.reportUrl || '',
          sessionId: item.sessionId || '',
          totalTokens: Number(item.totalTokens) || 0,
          totalCost: Number(item.totalCost) || 0.0
        }));
        setHistoryData(validatedItems);
      } else {
        setHistoryData([]);
      }
    } catch (err) {
      console.error('Error fetching analysis history:', err);
      const errorMessage = err instanceof Error && 'response' in err && 
        typeof err.response === 'object' && err.response !== null &&
        'data' in err.response && 
        typeof err.response.data === 'object' && err.response.data !== null &&
        'error' in err.response.data && 
        typeof err.response.data.error === 'string' 
        ? err.response.data.error 
        : 'Failed to load analysis history';
      setError(errorMessage);
      setHistoryData([]);
    } finally {
      setLoading(false);
    }
  };

  const fetchAnalysisReport = useCallback(async (jobId: string) => {
    try {
      setSelectedReportHtml('');
      const response = await apiClient.get(`/analysis_report/${jobId}`, {
        responseType: 'text'
      });
      
      if (typeof response.data === 'string') {
        setSelectedReportHtml(response.data);
      } else {
        console.error('Invalid report response format');
        setSelectedReportHtml('<p>Error: Invalid report format</p>');
      }
    } catch (err) {
      console.error('Error fetching analysis report:', err);
      const errorMessage = err instanceof Error && 'response' in err && 
        typeof err.response === 'object' && err.response !== null &&
        'data' in err.response && 
        typeof err.response.data === 'object' && err.response.data !== null &&
        'error' in err.response.data && 
        typeof err.response.data.error === 'string' 
        ? err.response.data.error 
        : 'Unknown error';
      setSelectedReportHtml(`<p>Error loading report: ${errorMessage}</p>`);
    }
  }, []);

  // Handle history item selection
  const handleHistorySelect = useCallback((item: AnalysisHistoryItem) => {
    setSelectedHistory(item);
    if (item.status === 'completed' && item.reportUrl) {
      fetchAnalysisReport(item.id);
    } else {
      setSelectedReportHtml('');
    }
  }, [fetchAnalysisReport]);

  // Check if selected item is in filtered results, clear selection if not
  useEffect(() => {
    if (selectedHistory && !filteredHistoryData.find(item => item.id === selectedHistory.id)) {
      // If currently selected item is not in filtered results, clear selection
      setSelectedHistory(null);
      setSelectedReportHtml('');
    }
  }, [filteredHistoryData, selectedHistory]);

  const getStatusBadge = useCallback((status: string) => {
    switch (status) {
      case 'completed':
        return <Badge className="bg-green-500 hover:bg-green-600 text-white text-xs px-3 py-1 rounded-full">Completed</Badge>;
      case 'failed':
        return <Badge className="bg-red-500 hover:bg-red-600 text-white text-xs px-3 py-1 rounded-full">Failed</Badge>;
      case 'running':
        return <Badge className="bg-blue-500 hover:bg-blue-600 text-white text-xs px-3 py-1 rounded-full">Running</Badge>;
      default:
        return <Badge variant="outline" className="text-xs px-3 py-1 rounded-full">Unknown</Badge>;
    }
  }, []);

  const handleDownloadPDF = useCallback(async () => {
    if (!selectedReportHtml || !selectedHistory) {
      return;
    }

    try {
      const response = await apiClient.post('/generate_pdf', {
        html: selectedReportHtml
      }, {
        responseType: 'blob'
      });
      
      // Create a blob link
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", `analysis_report_${selectedHistory.id}.pdf`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Error downloading PDF:', error);
      setError('Failed to generate PDF');
    }
  }, [selectedReportHtml, selectedHistory]);

  return (
    <div className="min-h-screen bg-gradient-dashboard">
      {/* Header */}
      <header className="border-b bg-card/50 backdrop-blur-sm">
        <div className="container mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-4">
              <Button 
                variant="ghost" 
                size="sm" 
                onClick={() => navigate('/analysis')}
                className="h-9 px-3 hover:bg-muted"
              >
                <ArrowLeft className="w-4 h-4 mr-2" />
                Back to Analysis
              </Button>
              <div className="h-6 w-px bg-border" />
              <h1 className="text-xl font-bold">Analysis History</h1>
            </div>
    
            <div className="flex items-center space-x-2">
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
                      <DropdownMenuItem onClick={() => navigate('/admin')}>
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
        {/* Left Panel: History List */}
        <div className="w-1/3 flex flex-col gap-4 h-full">
          {/* Search */}
          <Card className="flex-shrink-0 min-h-[140px]">
            <CardHeader className="pb-4 pt-4">
              <div className="flex items-center justify-between">
                <CardTitle className="text-lg">Search Analysis</CardTitle>
                <Button 
                  onClick={fetchAnalysisHistory} 
                  variant="ghost" 
                  size="sm"
                  className="h-8 w-8 p-0 hover:bg-muted"
                  title="Refresh history"
                  disabled={loading}
                >
                  <RotateCcw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input
                  placeholder="Search analysis queries..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-10 pr-10 h-10"
                  disabled={loading}
                />
                {searchQuery && !loading && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setSearchQuery('')}
                    className="absolute right-1 top-1/2 transform -translate-y-1/2 h-8 w-8 p-0 hover:bg-muted"
                    title="Clear search"
                  >
                    <X className="w-4 h-4" />
                  </Button>
                )}
              </div>
              <div className="text-xs text-muted-foreground flex items-center gap-1.5 px-2 py-1 bg-muted/50 rounded min-h-[24px]">
                <FileText className="w-3 h-3" />
                <span>
                  {loading 
                    ? 'Loading records...'
                    : error 
                      ? 'Failed to load records'
                      : filteredHistoryData.length === 0 && searchQuery
                        ? `No records match "${searchQuery}"`
                        : searchQuery 
                          ? `Found ${filteredHistoryData.length} of ${historyData.length} records`
                          : `Showing ${historyData.length} complete analysis records`
                  }
                </span>
              </div>
            </CardContent>
          </Card>

          {/* History List */}
          <Card className="flex-1 flex flex-col min-h-0">
            <CardHeader className="pb-4 pt-4 flex-shrink-0">
              <CardTitle className="text-lg">Analysis History</CardTitle>
              <CardDescription className="min-h-[20px]">
                {loading 
                  ? 'Loading analysis history...'
                  : 'Click on any analysis to view the full report'
                }
              </CardDescription>
            </CardHeader>
            <CardContent className="flex-1 p-0 min-h-0">
              <ScrollArea className="h-full px-4 pb-4">
                <div className="space-y-1">
                  {loading ? (
                    <div className="flex items-center justify-center text-center py-8">
                      <div>
                        <Loader2 className="w-8 h-8 text-muted-foreground mx-auto mb-4 animate-spin" />
                        <h3 className="text-lg font-medium mb-2">Loading History...</h3>
                        <p className="text-muted-foreground text-sm">
                          Retrieving completed analysis records from your sessions
                        </p>
                      </div>
                    </div>
                  ) : error ? (
                    <div className="flex items-center justify-center text-center py-12">
                      <div className="max-w-sm">
                        <div className="w-12 h-12 bg-red-100 rounded-full flex items-center justify-center mx-auto mb-4">
                          <Search className="w-6 h-6 text-red-600" />
                        </div>
                        <h3 className="text-lg font-medium mb-2">Error Loading History</h3>
                        <p className="text-muted-foreground text-sm mb-4 leading-relaxed">{error}</p>
                        <Button onClick={fetchAnalysisHistory} variant="outline" size="sm" className="px-6">
                          Try Again
                        </Button>
                      </div>
                    </div>
                  ) : filteredHistoryData.length === 0 ? (
                    <div className="flex items-center justify-center text-center py-12">
                      <div className="max-w-sm">
                        <div className="w-12 h-12 bg-muted rounded-full flex items-center justify-center mx-auto mb-4">
                          <Search className="w-6 h-6 text-muted-foreground" />
                        </div>
                        <h3 className="text-lg font-medium mb-2">
                          {searchQuery ? 'No Results Found' : 'No Analysis History'}
                        </h3>
                        <p className="text-muted-foreground text-sm leading-relaxed">
                          {searchQuery 
                            ? `No analysis found matching "${searchQuery}"` 
                            : historyData.length === 0
                              ? 'No completed analysis records found. Start analyzing data to build your history.'
                              : 'No analysis history available'
                          }
                        </p>
                        {!searchQuery && historyData.length === 0 && (
                          <div className="mt-4">
                            <Button 
                              onClick={() => navigate('/analysis')} 
                              variant="outline" 
                              size="sm"
                              className="px-6"
                            >
                              Start Your First Analysis
                            </Button>
                          </div>
                        )}
                      </div>
                    </div>
                  ) : (
                    filteredHistoryData.map((item) => (
                      <Card 
                        key={item.id}
                        className={`cursor-pointer transition-all duration-200 ${
                          selectedHistory?.id === item.id 
                            ? 'border-l-4 border-primary bg-primary/5' 
                            : 'border-l-4 border-transparent hover:bg-muted/30'
                        }`}
                        onClick={() => handleHistorySelect(item)}
                      >
                        <CardContent className="px-4 py-3">
                          <div className="space-y-2">
                            {/* Query and Status */}
                            <div className="flex items-start justify-between gap-3">
                              <h4 className="text-sm font-medium leading-5 flex-1 line-clamp-1">
                                {item.query || ""}
                              </h4>
                              {getStatusBadge(item.status)}
                            </div>
                            
                            {/* Metadata Row */}
                            <div className="flex items-center justify-between text-xs text-muted-foreground">
                              <div className="flex items-center">
                                <Calendar className="w-3 h-3 mr-1" />
                                <span>
                                  {item.timestamp 
                                    ? new Date(item.timestamp).toLocaleDateString()
                                    : 'Unknown date'
                                  }
                                </span>
                              </div>
                              <div className="flex items-center gap-4">
                                <span>{(item.totalTokens || 0).toLocaleString()} tokens</span>
                                <span>${(item.totalCost || 0).toFixed(4)}</span>
                              </div>
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                    ))
                  )}
                </div>
              </ScrollArea>
            </CardContent>
          </Card>
        </div>

        {/* Right Panel: Report Display */}
        <Card className="flex-1 flex flex-col h-full">
          <CardHeader className="pb-3 pt-4 flex-shrink-0">
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-lg">
                  {selectedHistory ? 'Analysis Report' : 'Select Analysis'}
                </CardTitle>
                 <CardDescription>
                   {selectedHistory 
                     ? `${selectedHistory.query.length > 60 ? selectedHistory.query.substring(0, 60) + '...' : selectedHistory.query} • ${selectedHistory.timestamp ? new Date(selectedHistory.timestamp).toLocaleDateString() : 'Unknown date'}`
                     : 'Choose a completed analysis from your history to view its detailed report'
                   }
                 </CardDescription>
              </div>
              {selectedReportHtml && (
                <Button onClick={handleDownloadPDF} variant="outline" size="sm">
                  <Download className="w-4 h-4 mr-2" />
                  Download PDF
                </Button>
              )}
            </div>
          </CardHeader>
          <CardContent className="flex-1 p-0 min-h-0">
            <ScrollArea className="h-full p-4">
              {!selectedHistory ? (
                <div className="flex items-center justify-center text-center h-full">
                  <div>
                    <History className="w-16 h-16 text-muted-foreground mx-auto mb-4" />
                    <h3 className="text-lg font-medium mb-2">No Analysis Selected</h3>
                    <p className="text-muted-foreground mb-4">
                      Select an analysis from the history list to view its detailed report
                    </p>
                  </div>
                </div>
              ) : selectedHistory.status === 'failed' ? (
                <div className="flex items-center justify-center text-center h-full">
                  <div>
                    <FileText className="w-16 h-16 text-muted-foreground mx-auto mb-4" />
                    <h3 className="text-lg font-medium mb-2">Analysis Failed</h3>
                    <p className="text-muted-foreground mb-4">
                      This analysis failed to complete. No report is available.
                    </p>
                    <div className="bg-muted p-4 rounded-lg text-left">
                      <p className="text-sm">
                        <strong>Query:</strong> {selectedHistory.query}
                      </p>
                      <p className="text-sm mt-2">
                        <strong>Status:</strong> Analysis failed to complete
                      </p>
                    </div>
                  </div>
                </div>
              ) : selectedHistory && selectedHistory.status === 'completed' && !selectedReportHtml ? (
                <div className="flex items-center justify-center text-center h-full">
                  <div>
                    <Loader2 className="w-8 h-8 text-muted-foreground mx-auto mb-4 animate-spin" />
                    <h3 className="text-lg font-medium mb-2">Loading Report...</h3>
                    <p className="text-muted-foreground text-sm">
                      Fetching analysis report from storage
                    </p>
                  </div>
                </div>
              ) : selectedReportHtml ? (
                <div>
                  {/* Query Info */}
                  {/* <Card className="mb-4">
                    <CardContent className="p-4">
                      <div className="space-y-2">
                         <div className="flex items-center space-x-4 text-xs text-muted-foreground">
                           <span>Status: {selectedHistory.status}</span>
                           <span>Tokens: {(selectedHistory.totalTokens || 0).toLocaleString()}</span>
                           <span>Cost: ${(selectedHistory.totalCost || 0).toFixed(4)}</span>
                           <span>Session: {selectedHistory.sessionId ? selectedHistory.sessionId.slice(-8) : 'Unknown'}</span>
                         </div>
                      </div>
                    </CardContent>
                  </Card> */}
                  
                  {/* Report Content */}
                  <div 
                    className="prose prose-sm max-w-none report-content"
                    dangerouslySetInnerHTML={{ __html: selectedReportHtml }} 
                  />
                </div>
              ) : selectedHistory ? (
                <div className="flex items-center justify-center text-center h-full">
                  <div>
                    <FileText className="w-16 h-16 text-muted-foreground mx-auto mb-4" />
                    <h3 className="text-lg font-medium mb-2">Report Not Available</h3>
                    <p className="text-muted-foreground mb-4">
                      The report for this analysis could not be loaded.
                    </p>
                    <div className="bg-muted p-4 rounded-lg text-left">
                      <p className="text-sm">
                        <strong>Query:</strong> {selectedHistory.query}
                      </p>
                      <p className="text-sm mt-2">
                        <strong>Status:</strong> {selectedHistory.status}
                      </p>
                      {selectedHistory.reportUrl && (
                        <p className="text-sm mt-2">
                          <strong>Storage:</strong> Report URL exists but content unavailable
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              ) : (
                <div className="flex items-center justify-center text-center h-full">
                  <div>
                    <History className="w-16 h-16 text-muted-foreground mx-auto mb-4" />
                    <h3 className="text-lg font-medium mb-2">Select Analysis</h3>
                    <p className="text-muted-foreground mb-4">
                      Choose a completed analysis from your history to view its detailed report
                    </p>
                  </div>
                </div>
              )}
            </ScrollArea>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default AnalysisHistory;