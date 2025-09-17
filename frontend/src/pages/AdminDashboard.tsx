import React, { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
  Users, 
  FileText, 
  TrendingUp, 
  Settings,
  LogOut,
  Activity,
  MoreHorizontal,
  Shield,
  UserCheck,
  UserX,
  RefreshCw,
  AlertTriangle,
  CheckCircle,
  Plus,
  Edit,
  Trash2,
  Coins,
  History,
  Save,
  X,
  Loader2,
  BrainCircuit,
  Brain
} from 'lucide-react';
import userService, { AdminStats, User, TokenHistoryRecord } from '@/services/userService';

const AdminDashboard: React.FC = () => {
  const { user, logout } = useAuth();
  const [activeTab, setActiveTab] = useState<'users' | 'stats' | 'settings'>('users');
  const [dashboardStats, setDashboardStats] = useState<AdminStats>({
    total_users: 0,
    total_reports: 0,
    total_tokens_used: 0,
    active_users: 0
  });
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // Modal states
  const [openUserModal, setOpenUserModal] = useState(false);
  const [openTokenModal, setOpenTokenModal] = useState(false);
  const [openHistoryModal, setOpenHistoryModal] = useState(false);
  const [modalMode, setModalMode] = useState<'create' | 'edit'>('create');
  const [selectedUser, setSelectedUser] = useState<User | null>(null);
  
  // Form states
  const [formData, setFormData] = useState({
    email: '',
    name: '',
    role: 'user',
    issued_token: undefined
  });
  const [formLoading, setFormLoading] = useState(false);
  
  // Token modal states
  const [tokensToAdd, setTokensToAdd] = useState(0);
  const [tokenReason, setTokenReason] = useState('');
  const [tokenLoading, setTokenLoading] = useState(false);
  
  // History modal states
  const [tokenHistory, setTokenHistory] = useState<TokenHistoryRecord[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  useEffect(() => {
    loadDashboardData();
  }, []);

  const loadDashboardData = async () => {
    try {
      setLoading(true);
      
      // Load stats using userService
      const stats = await userService.getAdminStats();
      setDashboardStats(stats);
      
      // Load users using userService
      const usersData = await userService.getAdminUsers();
      setUsers(usersData);
      
      setError(null);
    } catch (error: unknown) {
      console.error('Failed to load dashboard data:', error);
      setError('Failed to load dashboard data');
    } finally {
      setLoading(false);
    }
  };

  const handleToggleUserStatus = async (userEmail: string, isCurrentlyActive: boolean) => {
    try {
      const newStatus = !isCurrentlyActive;
      await userService.toggleUserStatus(userEmail, newStatus);
      
      // Update local state (handle both is_active boolean and status string)
      setUsers(users.map(u => 
        u.email === userEmail 
          ? { ...u, is_active: newStatus, status: newStatus ? 'active' : 'inactive' } as User
          : u
      ));
    } catch (error: unknown) {
      console.error('Failed to toggle user status:', error);
      setError('Failed to update user status');
    }
  };

  const handleChangeUserRole = async (userEmail: string, newRole: 'user' | 'admin') => {
    try {
      await userService.changeUserRole(userEmail, newRole);
      
      // Update local state
      setUsers(users.map(u => 
        u.email === userEmail 
          ? { ...u, role: newRole }
          : u
      ));
    } catch (error: unknown) {
      console.error('Failed to change user role:', error);
      setError('Failed to update user role');
    }
  };

  // Helper function to determine if user is active (handles both is_active boolean and status string) 
  const isUserActive = (userData: User): boolean => {
    // Check for boolean is_active field
    if (typeof userData.is_active === 'boolean') {
      return userData.is_active;
    }
    // Check for status string field (backend might return 'active'/'inactive')
    if ('status' in userData && typeof (userData as User & {status?: string}).status === 'string') {
      return (userData as User & {status: string}).status === 'active';
    }
    // Default to active if no status field
    return true;
  };

  // Create User Handler
  const handleCreateUser = () => {
    setModalMode('create');
    setSelectedUser(null);
    setFormData({
      email: '',
      name: '',
      role: 'user',
      issued_token: undefined
    });
    setOpenUserModal(true);
  };

  // Edit User Handler
  const handleEditUser = (userData: User) => {
    setModalMode('edit');
    setSelectedUser(userData);
    setFormData({
      email: userData.email,
      name: userData.name,
      role: userData.role,
      issued_token: userData.issued_token
    });
    setOpenUserModal(true);
  };

  // Delete User Handler
  const handleDeleteUser = async (userData: User) => {
    if (window.confirm(`Are you sure you want to delete user "${userData.name}"?`)) {
      try {
        await userService.deleteUser(userData.email);
        loadDashboardData();
        setError(null);
      } catch (error: unknown) {
        console.error('Failed to delete user:', error);
        setError('Failed to delete user. Please try again.');
      }
    }
  };

  // Add Tokens Handler
  const handleAddTokens = (userData: User) => {
    setSelectedUser(userData);
    setTokensToAdd(0);
    setTokenReason('');
    setOpenTokenModal(true);
  };

  // View Token History Handler
  const handleViewTokenHistory = async (userData: User) => {
    setSelectedUser(userData);
    setHistoryLoading(true);
    setOpenHistoryModal(true);
    
    try {
      const history = await userService.getUserTokenHistory(userData.email);
      setTokenHistory(history);
    } catch (error) {
      console.error('Failed to load token history:', error);
      setTokenHistory([]);
    } finally {
      setHistoryLoading(false);
    }
  };

  // Submit User Form
  const handleSubmitUserForm = async () => {
    try {
      setFormLoading(true);
      
      if (modalMode === 'create') {
        await userService.createUser(formData);
      } else {
        await userService.updateUser(selectedUser!.email, formData);
      }
      
      setOpenUserModal(false);
      loadDashboardData();
      setError(null);
    } catch (error: unknown) {
      console.error('Failed to save user:', error);
      setError(`Failed to ${modalMode} user. Please try again.`);
    } finally {
      setFormLoading(false);
    }
  };

  // Submit Add Tokens
  const handleSubmitAddTokens = async () => {
    try {
      setTokenLoading(true);
      
      await userService.addTokensToUser(
        selectedUser!.email, 
        tokensToAdd, 
        tokenReason || 'Admin allocation'
      );
      
      setOpenTokenModal(false);
      loadDashboardData();
      setError(null);
    } catch (error: unknown) {
      console.error('Failed to add tokens:', error);
      setError('Failed to add tokens. Please try again.');
    } finally {
      setTokenLoading(false);
    }
  };

  const StatsCard = ({ title, value, icon: Icon, className = "" }: { 
    title: string; 
    value: string | number; 
    icon: React.ComponentType<{ className?: string }>; 
    className?: string; 
  }) => (
    <Card className={className}>
      <CardContent className="flex items-center p-6">
        <div className="flex items-center space-x-4">
          <div className="p-2 bg-primary/10 rounded-lg">
            <Icon className="w-6 h-6 text-primary" />
          </div>
          <div>
            {loading ? (
              <div className="flex items-center space-x-2">
                <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
              </div>
            ) : (
              <p className="text-2xl font-bold">{value}</p>
            )}
            <p className="text-sm text-muted-foreground">{title}</p>
          </div>
        </div>
      </CardContent>
    </Card>
  );

  const UserManagement = () => (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold">User Management</h3>
          <p className="text-sm text-muted-foreground">Manage users, roles, and tokens</p>
        </div>
        <div className="flex gap-2">
          <Button onClick={handleCreateUser} variant="default" size="sm">
            <Plus className="w-4 h-4 mr-2" />
            Add User
          </Button>
          <Button onClick={loadDashboardData} variant="outline" size="sm" disabled={loading}>
            <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            {loading ? 'Refreshing...' : 'Refresh'}
          </Button>
        </div>
      </div>

      {loading ? (
         <Card>
           <CardContent className="p-6">
             <div className="flex items-center justify-center py-12">
               <div className="text-center">
                 <Loader2 className="w-8 h-8 animate-spin mx-auto mb-4 text-muted-foreground" />
                 <p className="text-lg font-medium text-muted-foreground">Loading user data...</p>
                 <p className="text-sm text-muted-foreground">Please wait while we fetch the latest information</p>
               </div>
             </div>
           </CardContent>
         </Card>
       ) : users.length === 0 ? (
         <Card>
           <CardContent className="p-6">
             <div className="text-center py-12 text-muted-foreground">
               <Users className="w-12 h-12 mx-auto mb-4 text-muted-foreground/50" />
               <h3 className="text-lg font-medium mb-2">No users found</h3>
               <p className="text-sm">There are no users in the system yet. Click "Add User" to create the first user.</p>
             </div>
           </CardContent>
         </Card>
       ) : (
         <Card>
           <Table>
             <TableHeader>
               <TableRow>
                 <TableHead>Name</TableHead>
                 <TableHead>Email</TableHead>
                 <TableHead>Role</TableHead>
                 <TableHead>Issued Tokens</TableHead>
                 <TableHead>Used Tokens</TableHead>
                 <TableHead>Reports</TableHead>
                 <TableHead className="w-[50px]">Actions</TableHead>
               </TableRow>
             </TableHeader>
             <TableBody>
               {users.map((userData) => (
                <TableRow key={userData.email}>
                  <TableCell>
                    <div className="flex items-center space-x-3">
                      <Avatar className="w-8 h-8">
                        <AvatarImage src={userData.picture} />
                        <AvatarFallback>
                          {userData.name?.charAt(0) || 'U'}
                        </AvatarFallback>
                      </Avatar>
                      <span className="font-medium">{userData.name}</span>
                    </div>
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {userData.email}
                  </TableCell>
                  <TableCell>
                    <Badge variant={userData.role === 'admin' ? 'default' : 'secondary'}>
                      {userData.role}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-sm font-medium">
                    {userData.issued_token?.toLocaleString() || 0}
                  </TableCell>
                  <TableCell className="text-sm">
                    <span className={userData.used_token > (userData.issued_token * 0.8) ? 'text-red-600 font-medium' : ''}>
                      {userData.used_token?.toLocaleString() || 0}
                    </span>
                  </TableCell>
                  <TableCell className="text-sm">
                    {userData.report_count || 0}
                  </TableCell>
                  <TableCell>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="sm">
                          <MoreHorizontal className="w-4 h-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => handleEditUser(userData)}>
                          <Edit className="w-4 h-4 mr-2" />
                          Edit User
                        </DropdownMenuItem>
                        
                        <DropdownMenuItem onClick={() => handleAddTokens(userData)}>
                          <Coins className="w-4 h-4 mr-2" />
                          Add Tokens
                        </DropdownMenuItem>
                        
                        <DropdownMenuItem onClick={() => handleViewTokenHistory(userData)}>
                          <History className="w-4 h-4 mr-2" />
                          Token History
                        </DropdownMenuItem>
                        
                        {/* <DropdownMenuItem
                          onClick={() => handleToggleUserStatus(userData.email, isUserActive(userData))}
                        >
                          {isUserActive(userData) ? (
                            <>
                              <UserX className="w-4 h-4 mr-2" />
                              Deactivate User
                            </>
                          ) : (
                            <>
                              <UserCheck className="w-4 h-4 mr-2" />
                              Activate User
                            </>
                          )}
                        </DropdownMenuItem> */}
                        
                        {/* {userData.role === 'user' ? (
                          <DropdownMenuItem
                            onClick={() => handleChangeUserRole(userData.email, 'admin')}
                          >
                            <Shield className="w-4 h-4 mr-2" />
                            Make Admin
                          </DropdownMenuItem>
                        ) : (
                          <DropdownMenuItem
                            onClick={() => handleChangeUserRole(userData.email, 'user')}
                          >
                            <Users className="w-4 h-4 mr-2" />
                            Make User
                          </DropdownMenuItem>
                        )} */}
                        
                        <DropdownMenuItem 
                          onClick={() => handleDeleteUser(userData)}
                          className="text-red-600 focus:text-red-600"
                        >
                          <Trash2 className="w-4 h-4 mr-2" />
                          Delete User
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}
    </div>
  );

  const renderTabContent = () => {
    switch (activeTab) {
      case 'users':
        return <UserManagement />;
      case 'stats':
        return (
           <div className="space-y-6">
             <h3 className="text-lg font-semibold">Detailed Statistics</h3>
             {loading ? (
               <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                 <Card>
                   <CardHeader>
                     <CardTitle>User Activity</CardTitle>
                   </CardHeader>
                   <CardContent>
                     <div className="flex items-center justify-center py-8">
                       <div className="text-center">
                         <Loader2 className="w-6 h-6 animate-spin mx-auto mb-2 text-muted-foreground" />
                         <p className="text-sm text-muted-foreground">Loading statistics...</p>
                       </div>
                     </div>
                   </CardContent>
                 </Card>
                 
                 <Card>
                   <CardHeader>
                     <CardTitle>System Usage</CardTitle>
                   </CardHeader>
                   <CardContent>
                     <div className="flex items-center justify-center py-8">
                       <div className="text-center">
                         <Loader2 className="w-6 h-6 animate-spin mx-auto mb-2 text-muted-foreground" />
                         <p className="text-sm text-muted-foreground">Loading statistics...</p>
                       </div>
                     </div>
                   </CardContent>
                 </Card>
               </div>
             ) : (
               <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                 <Card>
                   <CardHeader>
                     <CardTitle>User Activity</CardTitle>
                   </CardHeader>
                   <CardContent>
                     <div className="space-y-2">
                       <div className="flex justify-between">
                         <span>Total Users:</span>
                         <span className="font-semibold">{dashboardStats.total_users}</span>
                       </div>
                       <div className="flex justify-between">
                         <span>Active Users:</span>
                         <span className="font-semibold">{dashboardStats.active_users}</span>
                       </div>
                       <div className="flex justify-between">
                         <span>Inactive Users:</span>
                         <span className="font-semibold">
                           {dashboardStats.total_users - dashboardStats.active_users}
                         </span>
                       </div>
                     </div>
                   </CardContent>
                 </Card>
                 
                 <Card>
                   <CardHeader>
                     <CardTitle>System Usage</CardTitle>
                   </CardHeader>
                   <CardContent>
                     <div className="space-y-2">
                       <div className="flex justify-between">
                         <span>Total Reports:</span>
                         <span className="font-semibold">{dashboardStats.total_reports}</span>
                       </div>
                       <div className="flex justify-between">
                         <span>Tokens Consumed:</span>
                         <span className="font-semibold">
                           {dashboardStats.total_tokens_used.toLocaleString()}
                         </span>
                       </div>
                       <div className="flex justify-between">
                         <span>Avg Reports/User:</span>
                         <span className="font-semibold">
                           {dashboardStats.total_users > 0 
                             ? (dashboardStats.total_reports / dashboardStats.total_users).toFixed(1)
                             : '0'
                           }
                         </span>
                       </div>
                     </div>
                   </CardContent>
                 </Card>
               </div>
             )}
           </div>
         );
      case 'settings':
        return (
          <div className="space-y-6">
            <h3 className="text-lg font-semibold">System Settings</h3>
            <Card>
              <CardContent className="pt-6">
                <p className="text-muted-foreground">
                  System settings and configuration options will be available here.
                </p>
              </CardContent>
            </Card>
          </div>
        );
      default:
        return <UserManagement />;
    }
  };

  return (
    <div className="min-h-screen bg-gradient-dashboard">
      {/* Header */}
      <header className="border-b bg-card/50 backdrop-blur-sm">
        <div className="container mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-4">
              <h1 className="text-xl font-bold">
                <span className="flex items-center space-x-2">
                  <Brain className="w-6 h-6" />
                  <span>Admin Dashboard</span>
                </span>
              </h1>
            </div>

            <div className="flex items-center space-x-4">
              <Badge className="bg-orange-100 text-orange-800 hover:bg-orange-100">
                Admin
              </Badge>
              <div className="flex items-center space-x-3">
                <Avatar className="w-8 h-8">
                  <AvatarImage src={user?.picture} />
                  <AvatarFallback>
                    {user?.name?.charAt(0) || 'U'}
                  </AvatarFallback>
                </Avatar>
                <div className="hidden md:block">
                  <p className="text-sm font-medium">{user?.name}</p>
                  <p className="text-xs text-muted-foreground">{user?.email}</p>
                </div>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={logout}
              >
                <LogOut className="w-4 h-4 mr-2" />
                Logout
              </Button>
            </div>
          </div>
        </div>
      </header>

      <div className="container mx-auto px-6 py-6">
        {/* Stats Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          <StatsCard
            title="Total Users"
            value={dashboardStats.total_users}
            icon={Users}
          />
          <StatsCard
            title="Total Reports"
            value={dashboardStats.total_reports}
            icon={FileText}
          />
          <StatsCard
            title="Tokens Used"
            value={dashboardStats.total_tokens_used.toLocaleString()}
            icon={TrendingUp}
          />
          <StatsCard
            title="Active Users"
            value={dashboardStats.active_users}
            icon={Activity}
          />
        </div>

        {/* Error Alert */}
        {error && (
          <Alert variant="destructive" className="mb-6">
            <AlertTriangle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {/* Navigation Tabs */}
        {/* <Card className="mb-6">
          <CardContent className="p-4">
            <div className="flex space-x-2">
              <Button
                variant={activeTab === 'users' ? 'default' : 'outline'}
                onClick={() => setActiveTab('users')}
                size="sm"
              >
                <Users className="w-4 h-4 mr-2" />
                User Management
              </Button>
              
              <Button
                variant={activeTab === 'stats' ? 'default' : 'outline'}
                onClick={() => setActiveTab('stats')}
                size="sm"
              >
                <TrendingUp className="w-4 h-4 mr-2" />
                Statistics
              </Button>
              
              <Button
                variant={activeTab === 'settings' ? 'default' : 'outline'}
                onClick={() => setActiveTab('settings')}
                size="sm"
              >
                <Settings className="w-4 h-4 mr-2" />
                Settings
              </Button>
            </div>
          </CardContent>
        </Card> */}

        {/* Tab Content */}
        <Card>
          <CardContent className="p-6">
            {renderTabContent()}
          </CardContent>
        </Card>
      </div>

      {/* Create/Edit User Modal */}
      <Dialog open={openUserModal} onOpenChange={setOpenUserModal}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {modalMode === 'create' ? 'Create New User' : 'Edit User'}
            </DialogTitle>
            <DialogDescription>
              {modalMode === 'create' 
                ? 'Add a new user to the system with their basic information.'
                : 'Update user information and settings.'
              }
            </DialogDescription>
          </DialogHeader>
          
          <div className="space-y-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="email">Email Address</Label>
              <Input
                id="email"
                type="email"
                value={formData.email}
                onChange={(e) => setFormData({...formData, email: e.target.value})}
                disabled={modalMode === 'edit'}
                placeholder="user@example.com"
              />
            </div>
            
            <div className="flex flex-col gap-2">
              <Label htmlFor="name">Full Name</Label>
              <Input
                id="name"
                value={formData.name}
                onChange={(e) => setFormData({...formData, name: e.target.value})}
                placeholder="John Doe"
              />
            </div>
            
            <div className="flex flex-col gap-2">
              <Label htmlFor="role">Role</Label>
              <Select value={formData.role} onValueChange={(value) => setFormData({...formData, role: value})}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="user">User</SelectItem>
                  <SelectItem value="admin">Admin</SelectItem>
                </SelectContent>
              </Select>
            </div>
            
            <div className="flex flex-col gap-2">
              <Label htmlFor="tokens">{modalMode === 'edit' ? 'Issued Tokens' : 'Initial Tokens'}</Label>
              <Input
                id="tokens"
                type="number"
                value={formData.issued_token}
                onChange={(e) => setFormData({...formData, issued_token: parseInt(e.target.value)})}
                placeholder="0"
                disabled={modalMode === 'edit'}
              />
            </div>
          </div>
          
          <DialogFooter>
            <Button onClick={() => setOpenUserModal(false)} variant="outline" disabled={formLoading}>
              Cancel
            </Button>
            <Button onClick={handleSubmitUserForm} disabled={formLoading}>
              {formLoading ? (
                <>
                  <RefreshCw className="w-4 h-4  animate-spin" />
                  {modalMode === 'create' ? 'Creating...' : 'Updating...'}
                </>
              ) : (
                <>
                  <Save className="w-4 h-4 " />
                  {modalMode === 'create' ? 'Create User' : 'Update User'}
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Add Tokens Modal */}
      <Dialog open={openTokenModal} onOpenChange={setOpenTokenModal}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Tokens</DialogTitle>
            <DialogDescription>
              Add additional tokens to {selectedUser?.name}'s account.
            </DialogDescription>
          </DialogHeader>
          
          <div className="space-y-4">
            <div className="flex flex-col gap-2">
              <Label>Current Token Balance</Label>
              <div className="text-lg font-semibold">
                {selectedUser?.issued_token?.toLocaleString() || 0} tokens
              </div>
            </div>
            
            <div className="flex flex-col gap-2">
              <Label htmlFor="tokensToAdd">Tokens to Add</Label>
              <Input
                id="tokensToAdd"
                type="number"
                value={tokensToAdd}
                onChange={(e) => setTokensToAdd(parseInt(e.target.value) || 0)}
                placeholder="500"
                min="1"
              />
            </div>
            
            <div className="flex flex-col gap-2">
              <Label htmlFor="reason">Reason (Optional)</Label>
              <Textarea
                id="reason"
                value={tokenReason}
                onChange={(e) => setTokenReason(e.target.value)}
                placeholder="Reason for token allocation..."
                rows={3}
              />
            </div>
            
            {tokensToAdd > 0 && (
              <div className="p-3 bg-muted rounded-lg">
                <div className="text-sm font-medium">New Balance Preview:</div>
                <div className="text-lg font-semibold">
                  {((selectedUser?.issued_token || 0) + tokensToAdd).toLocaleString()} tokens
                </div>
              </div>
            )}
          </div>
          
          <DialogFooter>
            <Button onClick={() => setOpenTokenModal(false)} variant="outline" disabled={tokenLoading}>
              Cancel
            </Button>
            <Button onClick={handleSubmitAddTokens} disabled={tokenLoading || tokensToAdd <= 0}>
              {tokenLoading ? (
                <>
                  <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                  Adding...
                </>
              ) : (
                <>
                  <Coins className="w-4 h-4 mr-2" />
                  Add {tokensToAdd} Tokens
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Token History Modal */}
      <Dialog open={openHistoryModal} onOpenChange={setOpenHistoryModal}>
        <DialogContent className="max-w-4xl">
          <DialogHeader>
            <DialogTitle>Token History</DialogTitle>
            <DialogDescription>
              Token allocation history for {selectedUser?.name}
            </DialogDescription>
          </DialogHeader>
          
          <div className="space-y-4">
            {historyLoading ? (
              <div className="flex items-center justify-center py-8">
                <RefreshCw className="w-6 h-6 animate-spin mr-2" />
                Loading history...
              </div>
            ) : tokenHistory.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                No token history found
              </div>
            ) : (
              <div className="max-h-96 overflow-y-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Date</TableHead>
                      <TableHead>Tokens Added</TableHead>
                      <TableHead>Previous Balance</TableHead>
                      <TableHead>New Balance</TableHead>
                      <TableHead>Added By</TableHead>
                      <TableHead>Reason</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {tokenHistory.map((record, index) => (
                      <TableRow key={record.history_id || index}>
                        <TableCell className="text-sm">
                          {new Date(record.created_at).toLocaleDateString()}
                        </TableCell>
                        <TableCell className="text-sm font-medium text-green-600">
                          +{record.tokens_added?.toLocaleString()}
                        </TableCell>
                        <TableCell className="text-sm">
                          {record.previous_tokens?.toLocaleString()}
                        </TableCell>
                        <TableCell className="text-sm font-medium">
                          {record.new_total_tokens?.toLocaleString()}
                        </TableCell>
                        <TableCell className="text-sm">
                          {record.added_by}
                        </TableCell>
                        <TableCell className="text-sm">
                          {record.reason || 'No reason provided'}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </div>
          
          <DialogFooter>
            <Button onClick={() => setOpenHistoryModal(false)}>
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default AdminDashboard;
