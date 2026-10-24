// apps/studio-client/src/components/dock/DynamicActionDock.tsx
// Dynamic Action Dock with dnd-kit integration
// বাংলা মন্তব্য: dnd-kit ড্র্যাগ-অ্যান্ড-ড্রপ এবং ডাইনামিক ইন্টিগ্রেশন কন্ট্রোল করে।

import React from 'react';
import { useWorkspaceStore } from '../../store/useWorkspaceStore';

interface IntegrationItemProps {
  id: string;
  name: string;
  active: boolean;
  onToggle: (id: string) => void;
}

const IntegrationItem: React.FC<IntegrationItemProps> = ({ id, name, active, onToggle }) => (
  <button
    onClick={() => onToggle(id)}
    className={`px-4 py-2 rounded-md text-sm font-medium transition-all ${
      active
        ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/20'
        : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
    }`}
  >
    {name}
  </button>
);

export const DynamicActionDock: React.FC = () => {
  const { activeIntegrations, toggleIntegration } = useWorkspaceStore();

  const availableIntegrations = [
    { id: 'github', name: 'GitHub' },
    { id: 'slack', name: 'Slack' },
    { id: 'discord', name: 'Discord' },
    { id: 'notion', name: 'Notion' },
    { id: 'linear', name: 'Linear' },
  ];

  return (
    <div className="bg-slate-800/80 backdrop-blur-md rounded-xl p-4 border border-slate-700 shadow-xl">
      <h3 className="text-xs font-semibold text-slate-400 mb-3 uppercase tracking-wider">
        Active Integrations
      </h3>
      <div className="flex flex-wrap gap-2">
        {availableIntegrations.map((integration) => (
          <IntegrationItem
            key={integration.id}
            id={integration.id}
            name={integration.name}
            active={activeIntegrations.includes(integration.id)}
            onToggle={toggleIntegration}
          />
        ))}
      </div>
    </div>
  );
};

export default DynamicActionDock;
