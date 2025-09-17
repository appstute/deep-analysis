import React, { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { useSession } from '@/contexts/SessionContext';
import '@/styles/scrollbar.css';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Progress } from '@/components/ui/progress';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { 
  Upload as UploadIcon, 
  FileText, 
  LogOut,
  CheckCircle,
  AlertTriangle,
  Loader2,
  ChevronLeft,
  ChevronRight,
  Sparkles,
  Cross,
  X
} from 'lucide-react';
import { ValidateResponse, GenerateDomainResponse, SaveDomainResponse, DomainDictionary } from '@/types';
import apiClient from '@/services/apiService';
import { storageService } from '@/services/storageService';

const MAX_FILE_BYTES = 20 * 1024 * 1024; // 20MB
const ACCEPT_EXTENSIONS = ['csv', 'xlsx'];

const getFileExtension = (filename: string): string => {
  const idx = filename.lastIndexOf('.')
  if (idx === -1) return '';
  return filename.substring(idx + 1).toLowerCase();
};

const Upload: React.FC = () => {
  const { user, logout } = useAuth();
  const { sessionId, logoutAndCleanup, updateHasInputData } = useSession();
  const navigate = useNavigate();

  const [showRules, setShowRules] = useState(true);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [error, setError] = useState<string>('');
  const [errorsList, setErrorsList] = useState<string[]>([]);
  const [validating, setValidating] = useState<boolean>(false);
  const [validated, setValidated] = useState<boolean>(false);
  const [dragActive, setDragActive] = useState<boolean>(false);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [domain, setDomain] = useState<string>('');
  const [fileInfo, setFileInfo] = useState<string>('');
  const [underlying, setUnderlying] = useState<string>('');
  const [generating, setGenerating] = useState<boolean>(false);
  const [domainJson, setDomainJson] = useState<string>('');
  const [domainData, setDomainData] = useState(null);
  const [savedFilename, setSavedFilename] = useState<string>('');
  const [saving, setSaving] = useState<boolean>(false);
  const [activeStep, setActiveStep] = useState<number>(0); // 0 Validate, 1 Create, 2 Preview/Edit, 3 Final

  const handleUnauthorized = (status: number) => {
    if (status === 401 || status === 403) {
      return true;
    }
    return false;
  };

  const handleFilePicked = (file: File | null) => {
    setError('');
    setErrorsList([]);
    setValidated(false);
    if (!file) {
      setSelectedFile(null);
      return;
    }
    if (file.size > MAX_FILE_BYTES) {
      setError('File too large. Maximum allowed size is 20MB.');
      setSelectedFile(null);
      return;
    }
    const ext = getFileExtension(file.name);
    if (!ACCEPT_EXTENSIONS.includes(ext)) {
      setError('Invalid file type. Please upload a CSV or XLSX file.');
      setSelectedFile(null);
      return;
    }
    setSelectedFile(file);
  };

  const onInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files && e.target.files[0];
    handleFilePicked(file || null);
  };

  const onDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFilePicked(e.dataTransfer.files[0]);
    }
  };

  const onDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(true);
  };

  const onDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
  };

  const handleValidate = async () => {
    if (!selectedFile) {
      setError('Please select a file first.');
      return;
    }
    setError('');
    setErrorsList([]);
    setValidating(true);
    setValidated(false);
    setDomainJson('');
    setDomainData(null);
    setSavedFilename('');
    try {
      const form = new FormData();
      form.append('file', selectedFile);
      form.append('session_id', storageService.getSessionId() || '');

      const resp = await apiClient.post<ValidateResponse>('/validate_data', form, {
        headers: {
          'Content-Type': 'multipart/form-data'
        }
      });

      if (handleUnauthorized(resp.status)) return;

      if (resp.data.valid === true) {
        setValidated(true);
        setSavedFilename(resp.data.saved_file || selectedFile.name);
        updateHasInputData(true); // Update session context that we now have input data
        setActiveStep(1);
      } else {
        // Normalize errors and always show reasons if available
        const reasons = Array.isArray(resp.data?.errors)
          ? resp.data.errors.map((e) => String(e)).filter(Boolean)
          : (resp.data?.errors && typeof resp.data.errors === 'object'
              ? (() => {
                  try { return (Object.values(resp.data.errors)).flat().map(String).filter(Boolean); } catch { return Object.values(resp.data.errors).map(String); }
                })()
              : []);

        const message = reasons.length
          ? reasons.join('; ')
          : (typeof resp.data?.error === 'string' ? resp.data.error : '');

        setErrorsList(reasons);
        setError(message || 'Validation failed');
      }
    } catch (err) {
      setError(err?.message || 'Validation error');
    } finally {
      setValidating(false);
    }
  };

  const handleGenerateDomain = async () => {
    if (!validated) {
      setError('Please validate the file first.');
      return;
    }
    if (!savedFilename) {
      setError('No saved file found. Please validate the file first.');
      return;
    }
    setError('');
    setErrorsList([]);
    setGenerating(true);
    setDomainJson('');
    try {
      const resp = await apiClient.post<GenerateDomainResponse>('/generate_domain_dictionary', {
          domain: domain,
          file_info: fileInfo,
          filename: savedFilename,
          underlying_conditions_about_dataset: underlying,
          session_id: storageService.getSessionId() || ''
      });

      if (handleUnauthorized(resp.status)) return;

      if (resp.data.domain_dictionary) {
        setDomainData(resp.data.domain_dictionary);
        setDomainJson(JSON.stringify(resp.data.domain_dictionary, null, 2));
        setActiveStep(2);
      } else {
        setError(resp.data?.error || 'Failed to generate domain dictionary');
      }
    } catch (err) {
      setError(err?.message || 'Generation error');
    } finally {
      setGenerating(false);
    }
  };

  const openFilePicker = () => inputRef.current?.click();

  const handleGoToAnalysis = () => {
    navigate('/analysis');
  };

  const handleSaveDomainDictionary = async (): Promise<boolean> => {
    if (!domainData) {
      setError('No domain dictionary to save.');
      return false;
    }
    setSaving(true);
    setError('');
    try {
      const resp = await apiClient.post<SaveDomainResponse>('/save_domain_dictionary', {
          domain_dictionary: domainData,
          session_id: storageService.getSessionId() || ''
      });

      if (handleUnauthorized(resp.status)) return false;

      if (resp.data) {
        return true; // Success
      } else {
        setError((resp.data as SaveDomainResponse)?.error || 'Failed to save domain dictionary');
        return false;
      }
    } catch (err) {
      setError(err?.message || 'Save error');
      return false;
    } finally {
      setSaving(false);
    }
  };

  const steps = ['Upload & Validate', 'Create Domain Knowledge', 'Preview & Edit', 'Complete'];

  const getStepContent = (step: number) => {
    switch (step) {
      case 0:
        return (
          <div className="space-y-8">
            <div>
              <h3 className="text-lg font-semibold mb-3">Upload & Validate Data</h3>
              <p className="text-muted-foreground mb-4">
                Upload your CSV or XLSX file and validate its structure and content
              </p>
            </div>

            <div
              className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors ${
                dragActive 
                  ? 'border-primary bg-primary/5' 
                  : 'border-border hover:border-primary/50'
              }`}
              onDrop={onDrop}
              onDragOver={onDragOver}
              onDragLeave={onDragLeave}
            >
              <UploadIcon className="mx-auto h-12 w-12 text-muted-foreground mb-4" />
              <p className="text-lg font-medium mb-2">Drag and drop your file here</p>
              <p className="text-muted-foreground mb-4">Max 20MB. CSV or XLSX files only</p>
              <Button onClick={openFilePicker} variant="outline">
                Choose File
              </Button>
              <input
                ref={inputRef}
                type="file"
                accept=".csv,.xlsx"
                onChange={onInputChange}
                className="hidden"
              />
            </div>

            {selectedFile && (
              <div className="flex items-center space-x-3 p-4 bg-muted rounded-lg">
                <FileText className="h-5 w-5 text-muted-foreground" />
                <div className="flex-1">
                  <p className="font-medium">{selectedFile.name}</p>
                  <p className="text-sm text-muted-foreground">
                    {(selectedFile.size / (1024 * 1024)).toFixed(2)} MB
                  </p>
                </div>
                {validated && <CheckCircle className="h-5 w-5 text-green-600" />}
              </div>
            )}

            <Button 
              onClick={handleValidate} 
              disabled={!selectedFile || validating} 
              className="w-full"
            >
              {validating ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Validating...
                </>
              ) : (
                'Validate File'
              )}
            </Button>

            {validated && (
              <Alert>
                <CheckCircle className="h-4 w-4" />
                <AlertDescription>
                  File validation successful! You can proceed to the next step.
                </AlertDescription>
              </Alert>
            )}
          </div>
        );

      case 1:
        return (
          <div className="space-y-8">
            <div>
              <h3 className="text-lg font-semibold mb-3">Create Domain Knowledge</h3>
              <p className="text-muted-foreground mb-4">
                Provide context about your data to generate a comprehensive domain dictionary
              </p>
            </div>

            <div className="space-y-6">
              <div className="flex flex-col gap-2">
                <Label htmlFor="domain">Domain *</Label>
                <Input
                  id="domain"
                  placeholder="e.g., Banking and financial services, E-commerce sales data"
                  value={domain}
                  onChange={(e) => setDomain(e.target.value)}
                />
              </div>

              <div className="flex flex-col gap-2">
                <Label htmlFor="fileInfo">File Information *</Label>
                <Input
                  id="fileInfo"
                  placeholder="e.g., Customer transaction data with payment details"
                  value={fileInfo}
                  onChange={(e) => setFileInfo(e.target.value)}
                />
              </div>

              <div className="flex flex-col gap-2">
                <Label htmlFor="underlying">Business Rules & Conditions</Label>
                <Textarea
                  id="underlying"
                  placeholder="e.g., CustomerID is null for guest users, Amount is 0 for cancelled orders"
                  value={underlying}
                  onChange={(e) => setUnderlying(e.target.value)}
                  rows={4}
                />
                <p className="text-sm text-muted-foreground mt-1">
                  Separate multiple conditions with commas or new lines
                </p>
              </div>
            </div>

            <Button 
              onClick={handleGenerateDomain} 
              disabled={generating || !domain.trim() || !fileInfo.trim()}
              className="w-full"
            >
              {generating ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Generating Domain Dictionary...
                </>
              ) : (
                <>
                  <Sparkles className="mr-2 h-4 w-4" />
                  Generate Domain Dictionary
                </>
              )}
            </Button>
          </div>
        );

      case 2:
        return (
          <div className="space-y-8">
            <div>
              <h3 className="text-lg font-semibold mb-3">Review & Edit Domain Dictionary</h3>
              <p className="text-muted-foreground mb-4">
                Review and customize the generated domain dictionary
              </p>
            </div>

            {domainData ? (
              <div className="space-y-8 max-h-[500px] overflow-y-auto custom-scrollbar p-4 ">
                {/* Domain Description */}
                <div className="flex flex-col gap-2">
                  <Label htmlFor="domainDesc">Domain Description</Label>
                  <Textarea
                    id="domainDesc"
                    value={domainData.domain || ''}
                    onChange={(e) => {
                      const updated = { ...domainData, domain: e.target.value };
                      setDomainData(updated);
                      setDomainJson(JSON.stringify(updated, null, 2));
                    }}
                    rows={2}
                  />
                </div>

                {/* Columns */}
                <div>
                  <Label className="text-base font-medium">Column Descriptions</Label>
                  <div className="mt-2">
                    <Accordion type="single" collapsible className="w-full">
                      {domainData.columns && domainData.columns.map((column, idx: number) => (
                        <AccordionItem key={idx} value={`column-${idx}`} className="border rounded-lg mb-2">
                          <AccordionTrigger className="px-4 py-3 hover:no-underline">
                            <div className="flex items-center space-x-2">
                              <span className="font-medium text-sm">{column.name}</span>
                              <Badge variant="secondary" className="text-xs">
                                {column.dtype}
                              </Badge>
                            </div>
                          </AccordionTrigger>
                          <AccordionContent className="px-4 pb-4">
                            <Textarea
                              value={column.description || ''}
                              onChange={(e) => {
                                const updatedColumns = [...domainData.columns];
                                updatedColumns[idx] = { ...column, description: e.target.value };
                                const updated = { ...domainData, columns: updatedColumns };
                                setDomainData(updated);
                                setDomainJson(JSON.stringify(updated, null, 2));
                              }}
                              rows={3}
                              placeholder="Enter a detailed description for this column..."
                              className="text-sm"
                            />
                          </AccordionContent>
                        </AccordionItem>
                      ))}
                    </Accordion>
                  </div>
                </div>

                {/* Business Rules */}
                <div>
                  <Label className="text-base font-medium">Business Rules & Conditions</Label>
                  <div className="mt-3 space-y-3">
                    {domainData.underlying_conditions_about_dataset && domainData.underlying_conditions_about_dataset.map((rule: string, idx: number) => (
                      <div key={idx} className="flex space-x-2 items-center justify-center">
                        <Textarea
                          value={rule || ''}
                          onChange={(e) => {
                            const updatedRules = [...domainData.underlying_conditions_about_dataset];
                            updatedRules[idx] = e.target.value;
                            const updated = { ...domainData, underlying_conditions_about_dataset: updatedRules };
                            setDomainData(updated);
                            setDomainJson(JSON.stringify(updated, null, 2));
                          }}
                          rows={2}
                          placeholder="Enter business rule or condition..."
                        />
                        {/* <Button
                          variant=""
                          size="sm"
                         
                        > */}
                          <X className="w-5 h-5 text-red-500 "   onClick={() => {
                            const updatedRules = domainData.underlying_conditions_about_dataset.filter((_, i: number) => i !== idx);
                            const updated = { ...domainData, underlying_conditions_about_dataset: updatedRules };
                            setDomainData(updated);
                            setDomainJson(JSON.stringify(updated, null, 2));
                          }} />
                        {/* </Button> */}
                      </div>
                    ))}
                    <Button
                      variant="outline"
                      onClick={() => {
                        const updated = {
                          ...domainData,
                          underlying_conditions_about_dataset: [...(domainData.underlying_conditions_about_dataset || []), '']
                        };
                        setDomainData(updated);
                        setDomainJson(JSON.stringify(updated, null, 2));
                      }}
                    >
                      Add Rule
                    </Button>
                  </div>
                </div>
              </div>
            ) : (
              <div className="text-center py-8 text-muted-foreground">
                No domain dictionary generated yet. Please complete the previous step.
              </div>
            )}

            <Button 
              onClick={async () => {
                const success = await handleSaveDomainDictionary();
                if (success) {
                  setActiveStep(3);
                }
              }}
              disabled={saving || !domainData}
              className="w-full"
            >
              {saving ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Saving...
                </>
              ) : (
                <>
                  <CheckCircle className="mr-2 h-4 w-4" />
                  Confirm & Save Domain Dictionary
                </>
              )}
            </Button>
          </div>
        );

      case 3:
        return (
          <div className="text-center space-y-8">
            <div className="text-6xl">🎉</div>
            <div>
              <h3 className="text-xl font-semibold text-green-600 mb-2">
                Setup Complete!
              </h3>
              <p className="text-muted-foreground mb-6">
                Your data and domain dictionary have been successfully saved and are ready for analysis.
              </p>
            </div>

            <div className="bg-green-50 border border-green-200 rounded-lg p-4 space-y-3">
              <div className="flex items-center justify-center space-x-2">
                <FileText className="h-5 w-5 text-green-600" />
                <span className="font-medium text-green-800">Data File: Validated and saved</span>
              </div>
              <div className="flex items-center justify-center space-x-2">
                <CheckCircle className="h-5 w-5 text-green-600" />
                <span className="font-medium text-green-800">Domain Dictionary: Generated and saved</span>
              </div>
            </div>

            <Button onClick={handleGoToAnalysis} size="lg" className="w-full">
              🚀 Go to Deep Insights
            </Button>
          </div>
        );

      default:
        return null;
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
                  <Badge variant={user?.role === 'admin' ? 'default' : 'secondary'} className="text-xs">
                    {user?.role}
                  </Badge>
                </div>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={logoutAndCleanup}
              >
                <LogOut className="w-4 h-4 mr-2" />
                Sign Out
              </Button>
            </div>
          </div>
        </div>
      </header>

      {/* Stepper */}
      <div className="bg-muted/50 border-b">
        <div className="container mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            {steps.map((step, index) => (
              <div key={step} className="flex items-center">
                <div className={`flex items-center space-x-2 ${
                  index <= activeStep ? 'text-primary' : 'text-muted-foreground'
                }`}>
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium ${
                    index < activeStep 
                      ? 'bg-primary text-primary-foreground' 
                      : index === activeStep 
                        ? 'bg-primary text-primary-foreground' 
                        : 'bg-muted text-muted-foreground'
                  }`}>
                    {index < activeStep ? <CheckCircle className="w-4 h-4" /> : index + 1}
                  </div>
                  <span className="text-sm font-medium">{step}</span>
                </div>
                {index < steps.length - 1 && (
                  <div className="w-16 h-0.5 bg-border mx-4" />
                )}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Main Content */}
      <main className="container mx-auto px-8 py-12">
        <div className="max-w-3xl mx-auto">
          <Card className="shadow-lg">
            <CardContent className="p-8">
              {getStepContent(activeStep)}
            </CardContent>
          </Card>

          {/* Navigation */}
          <div className="flex justify-between mt-8">
            <Button
              variant="outline"
              onClick={() => setActiveStep(Math.max(0, activeStep - 1))}
              disabled={activeStep === 0}
            >
              <ChevronLeft className="w-4 h-4 mr-2" />
              Previous
            </Button>
            
            {activeStep < steps.length - 1 && activeStep !== 2 && (
              <Button
                onClick={() => setActiveStep(Math.min(steps.length - 1, activeStep + 1))}
                disabled={
                  (activeStep === 0 && !validated) ||
                  (activeStep === 1 && !domainData)
                }
              >
                Next
                <ChevronRight className="w-4 h-4 ml-2" />
              </Button>
            )}
          </div>

          {/* Error Display */}
          {(error || errorsList.length > 0) && (
            <Alert variant="destructive" className="mt-8">
              <AlertTriangle className="h-4 w-4" />
              <AlertDescription>
                {error && <div>{error}</div>}
                {errorsList.length > 0 && (
                  <ul className="list-disc list-inside mt-2">
                    {errorsList.map((err, i) => (
                      <li key={i}>{err}</li>
                    ))}
                  </ul>
                )}
              </AlertDescription>
            </Alert>
          )}
        </div>
      </main>

      {/* Bottom Spacing */}
      <div className="pb-16"></div>

      {/* Rules Modal */}
      {showRules && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <Card className="w-full max-w-md mx-4">
            <CardHeader>
              <CardTitle>File Upload Rules</CardTitle>
            </CardHeader>
            <CardContent>
              <ol className="list-decimal list-inside space-y-2 text-sm">
                <li>Upload data file (.csv or .xlsx, ≤20MB)</li>
                <li>First row must be headers; no duplicate/empty headers</li>
                <li>Max 30 columns and 500,000 rows</li>
                <li>Columns must be text-like (no JSON/blob/base64 images)</li>
              </ol>
              <Button onClick={() => setShowRules(false)} className="w-full mt-4">
                Got it
              </Button>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
};

export default Upload;
