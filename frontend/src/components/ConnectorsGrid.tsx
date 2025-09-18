import React from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { ChevronRight } from 'lucide-react';

export type ConnectorKey = 'upload' | 'salesforce' ;

export interface ConnectorItem {
  key: ConnectorKey;
  title: string;
  description: string;
  icon: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
  comingSoonLabel?: string;
}

interface ConnectorsGridProps {
  items: ConnectorItem[];
  className?: string;
}

const ConnectorsGrid: React.FC<ConnectorsGridProps> = ({ items, className }) => {
  return (
    <div className={`grid grid-cols-1 sm:grid-cols-2 gap-4 ${className || ''}`}>
      {items.map((item) => {
        const isDisabled = item.disabled === true;
        return (
          <Card
            key={item.key}
            className={`${isDisabled ? 'relative cursor-not-allowed opacity-60 saturate-0' : 'cursor-pointer hover:shadow-md transition'}`}
            onClick={() => {
              if (!isDisabled) item.onClick();
            }}
          >
            <CardContent className="p-4">
              <div className="flex items-start gap-3">
                {item.icon}
                <div className="flex-1">
                  <div className="font-medium text-foreground">{item.title}</div>
                  <div className="text-sm text-muted-foreground">{item.description}</div>
                </div>
                <ChevronRight className="w-4 h-4 text-muted-foreground mt-1" />
              </div>
              {isDisabled && (
                <div className="absolute top-2 right-2 text-[11px] px-2 py-0.5 rounded-full bg-muted text-muted-foreground border">
                  {item.comingSoonLabel || 'Coming soon'}
                </div>
              )}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
};

export default ConnectorsGrid;


