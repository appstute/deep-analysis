import React from 'react';
import ConnectorForm, { FieldConfig } from '@/components/ConnectorForm';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { useNavigate } from 'react-router-dom';
import { storageService } from '@/services/storageService';
import apiClient from '@/services/apiService';

const SalesforceConnector: React.FC = () => {
  const navigate = useNavigate();

  const fields: FieldConfig[] = [
    { name: 'clientId', label: 'Client ID', placeholder: 'OAuth Consumer Key', type: 'text', required: true },
    { name: 'clientSecret', label: 'Client Secret', placeholder: 'OAuth Consumer Secret', type: 'password', required: true },
    { name: 'username', label: 'Username', placeholder: 'user@example.com', type: 'text', required: true },
    { name: 'password', label: 'Password', placeholder: 'Your Salesforce password', type: 'password', required: true },
    { name: 'securityToken', label: 'Security Token', placeholder: 'Salesforce security token', type: 'password', required: true }
  ];

  const onSubmit = async (values: Record<string, string>) => {
    // TODO: replace with API call to persist connection
    console.log('Salesforce config', values);
         // get email from user session in storageService
      const user = storageService.getUser();
      const email = user?.email;
      const sessionId = storageService.getSessionId();

      if (!email) {
        throw new Error('No email found in session. Please login again.');
      }
      else{
         const payload = {
        "user_email": email,    
        "session_id":sessionId,
        "client_id": values.clientId,
        "client_secret": values.clientSecret,
        "username": values.username,
        "password": values.password,
        "security_key": values.securityToken
      };
        console.log('[SalesforceConnector] Submitting config:', payload);

      // call backend API
      const res = await apiClient.post('/salesforce/save_credentials', payload);
      if (res['status_code'] == 200) {
        console.log('[SalesforceConnector] API response:', res.data);
      }
         navigate('/analysis')

      }
  };


  return (
    <div className="container mx-auto px-6 py-8">
      <div className="max-w-2xl mx-auto">
        <Card>

          <CardContent>
            <ConnectorForm
              title="Salesforce Credentials"
              description="We store credentials securely. You can revoke access at any time."
              fields={fields}
              onSubmit={onSubmit}
              submitLabel="Connect Salesforce"
            />
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default SalesforceConnector;


