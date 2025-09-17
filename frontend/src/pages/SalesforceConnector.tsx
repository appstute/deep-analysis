import React, { useState } from 'react';
import ConnectorForm, { FieldConfig } from '@/components/ConnectorForm';
import { useNavigate } from 'react-router-dom';
import { Dialog, DialogContent } from '@/components/ui/dialog';

const SalesforceConnector: React.FC = () => {
  const navigate = useNavigate();

  const fields: FieldConfig[] = [
    { name: 'clientId', label: 'Client ID', placeholder: 'OAuth Consumer Key', type: 'text', required: true },
    { name: 'clientSecret', label: 'Client Secret', placeholder: 'OAuth Consumer Secret', type: 'password', required: true },
    { name: 'username', label: 'Username', placeholder: 'user@example.com', type: 'text', required: true },
    { name: 'password', label: 'Password', placeholder: 'Your Salesforce password', type: 'password', required: true },
    { name: 'securityToken', label: 'Security Token', placeholder: 'Salesforce security token', type: 'password', required: true },
  ];

  const onSubmit = async (values: Record<string, string>) => {
    // TODO: replace with API call to persist connection
    console.log('Salesforce config', values);
    navigate('/');
  };

  const [open, setOpen] = useState(true);

  const handleOpenChange = (next: boolean) => {
    setOpen(next);
    if (!next) navigate(-1);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-[600px]">
        <div className="h-[520px] overflow-y-auto pr-1">
          <ConnectorForm
            title="Salesforce Credentials"
            description='Provide credentials to authorize access to your Salesforce data.'
            fields={fields}
            onSubmit={onSubmit}
            submitLabel="Connect Salesforce"
            inputClassName="h-9 px-2 py-1 text-sm"
            spacingClassName="space-y-3"
          />
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default SalesforceConnector;


