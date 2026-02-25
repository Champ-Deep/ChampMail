import React from 'react';
import { Card } from './Card';

interface EmptyStateProps {
  icon: React.ElementType;
  title: string;
  description: string;
}

export function EmptyState({ icon: Icon, title, description }: EmptyStateProps) {
  return (
    <Card className="bg-brand-purple/5 border-brand-purple/20">
      <div className="p-6 text-center">
        <Icon className="w-12 h-12 text-brand-purple mx-auto mb-3" />
        <h3 className="text-lg font-semibold text-gray-900 mb-2">{title}</h3>
        <p className="text-gray-600">{description}</p>
      </div>
    </Card>
  );
}
