import React, { useState } from 'react';
import { getApiBaseUrl } from '../../utils/api';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { PluginMarketplace } from './plugins/PluginMarketplace';
import { MCPConnector } from '../../components/plugins/MCPConnector';

export const IntegrationsManager: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'plugins' | 'mcp' | 'system'>('plugins');
  const [githubStatus] = useState<'Disconnected' | 'Connected'>('Disconnected');

  const handleGithubConnect = () => {
    const API_BASE = getApiBaseUrl();
    window.location.href = `${API_BASE}/api/v1/integrations/github/link`;
  };

  return (
    <div className="w-full">
      <div className="flex border-b border-gray-200 mb-6 px-8 pt-8 max-w-7xl mx-auto">
        <button
          className={`py-3 px-6 font-medium text-sm focus:outline-none ${activeTab === 'plugins' ? 'border-b-2 border-primary text-primary' : 'text-gray-500 hover:text-gray-700'}`}
          onClick={() => setActiveTab('plugins')}
        >
          Plugin Marketplace (V2.1)
        </button>
        <button
          className={`py-3 px-6 font-medium text-sm focus:outline-none ${activeTab === 'mcp' ? 'border-b-2 border-primary text-primary' : 'text-gray-500 hover:text-gray-700'}`}
          onClick={() => setActiveTab('mcp')}
        >
          MCP Servers
        </button>
        <button
          className={`py-3 px-6 font-medium text-sm focus:outline-none ${activeTab === 'system' ? 'border-b-2 border-primary text-primary' : 'text-gray-500 hover:text-gray-700'}`}
          onClick={() => setActiveTab('system')}
        >
          System Integrations (Legacy)
        </button>
      </div>

      {activeTab === 'plugins' ? (
        <PluginMarketplace />
      ) : activeTab === 'mcp' ? (
        <div className="px-8 pb-12">
          <MCPConnector />
        </div>
      ) : (
        <div className="p-8 max-w-7xl mx-auto space-y-8">
          <div>
            <h1 className="text-3xl font-bold mb-2">🔗 System Integrations</h1>
            <p className="text-[var(--supremeai-color-neutral-500)]">
              Core platform infrastructure connections (e.g., n8n, Appwrite). Note: GitHub is migrating to the Plugin Marketplace.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* 🟢 GitHub Card (Active) */}
            <Card className="hover:border-[var(--supremeai-color-brand-primary-light)] dark:hover:border-[var(--supremeai-color-brand-primary-dark)] transition-colors">
              <CardHeader className="text-center">
                <div className="text-5xl mb-2">🐙</div>
                <CardTitle>GitHub (Legacy Auth)</CardTitle>
                <CardDescription>
                  Legacy OAuth connection.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Button
                  onClick={handleGithubConnect}
                  variant={githubStatus === 'Connected' ? 'secondary' : 'primary'}
                  className="w-full"
                >
                  {githubStatus === 'Connected' ? '✅ Connected' : 'Connect GitHub'}
                </Button>
              </CardContent>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
};
