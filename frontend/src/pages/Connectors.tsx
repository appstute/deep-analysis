import React from 'react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Upload, Cloud, Database } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import ConnectorsGrid, { ConnectorItem } from '@/components/ConnectorsGrid';

const Connectors: React.FC = () => {
  const navigate = useNavigate();

  const items: ConnectorItem[] = [
    {
      key: 'upload',
      title: 'Upload File',
      description: 'CSV, Excel, or JSON files',
      icon: (
        <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center">
          <Upload className="w-5 h-5 text-primary" />
        </div>
      ),
      onClick: () => navigate('/upload'),
    },
    {
      key: 'salesforce',
      title: 'Salesforce',
      description: 'Connect your Salesforce org',
      icon: (
        <div className="w-10 h-10 rounded-xl bg-blue-500/10 flex items-center justify-center">
          <Cloud className="w-5 h-5 text-blue-500" />
        </div>
      ),
      onClick: () => navigate('/connect/salesforce'),
    },
    {
      key: 'sql',
      title: 'SQL Database',
      description: 'MySQL, Postgres, SQL Server',
      icon: (
        <div className="w-10 h-10 rounded-xl bg-emerald-500/10 flex items-center justify-center">
          <Database className="w-5 h-5 text-emerald-600" />
        </div>
      ),
      onClick: () => {},
      disabled: true,
      comingSoonLabel: 'Coming soon',
    },
  ];

  return (
    <div className="p-6">
      <Dialog>
        <DialogTrigger asChild>
          <Button>
            Choose Connector
          </Button>
        </DialogTrigger>
        <DialogContent className="sm:max-w-[560px]">
          <DialogHeader>
            <DialogTitle>Choose a data connector</DialogTitle>
            <DialogDescription>
              Pick where your data lives. You can add more connectors later.
            </DialogDescription>
          </DialogHeader>
          <ConnectorsGrid items={items} />
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default Connectors;


