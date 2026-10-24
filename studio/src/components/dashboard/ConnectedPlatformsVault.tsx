import React, { useEffect, useState } from 'react';
import { apiClient } from '../../services/apiClient';
import OneLinerMCPConnect from './OneLinerMCPConnect';

interface PlatformCredential {
  id: string;
  name: string;
  platform: string;
  connected: boolean;
  lastAccessed: string;
  permissions: string[];
  status: 'active' | 'revoked' | 'expired' | 'pending';
}

const ConnectedPlatformsVault: React.FC = () => {
  const [platforms, setPlatforms] = useState<PlatformCredential[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    apiClient.get<PlatformCredential[] | { platforms?: PlatformCredential[] }>('/api/v1/integrations')
      .then((response) => {
        if (!active) return;
        setPlatforms(Array.isArray(response) ? response : response.platforms ?? []);
      })
      .catch(() => { if (active) setLoadError('Unable to load connected platforms.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const [showAddModal, setShowAddModal] = useState(false);
  const [newPlatform, setNewPlatform] = useState({
    name: '',
    platform: '',
    credentials: ''
  });
  const [selectedPlatform, setSelectedPlatform] = useState<PlatformCredential | null>(null);
  const [showDetails, setShowDetails] = useState(false);

  const platformIcons: Record<string, string> = {
    'GitHub': '🐙',
    'Google Cloud': '☁️',
    'AWS': '.AWS',
    'DigitalOcean': '🌊',
    'Azure': '.Azure',
    'Slack': '💬',
    'Discord': '🎮',
    'Jira': '📋',
    'Notion': '📝'
  };

  const handleAddPlatform = () => {
    if (newPlatform.name && newPlatform.platform && newPlatform.credentials) {
      const newEntry: PlatformCredential = {
        id: `new_${Date.now()}`,
        name: newPlatform.name,
        platform: newPlatform.platform,
        connected: true,
        lastAccessed: new Date().toISOString(),
        permissions: ['read', 'write'], // Default permissions
        status: 'active'
      };

      setPlatforms([...platforms, newEntry]);
      setNewPlatform({ name: '', platform: '', credentials: '' });
      setShowAddModal(false);
    }
  };

  const handleToggleConnection = (id: string) => {
    setPlatforms(platforms.map(platform =>
      platform.id === id
        ? {
            ...platform,
            connected: !platform.connected,
            status: !platform.connected ? 'active' : 'revoked',
            lastAccessed: new Date().toISOString()
          }
        : platform
    ));
  };

  const handleDelete = (id: string) => {
    setPlatforms(platforms.filter(platform => platform.id !== id));
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active': return 'text-green-500';
      case 'revoked': return 'text-red-500';
      case 'expired': return 'text-yellow-500';
      case 'pending': return 'text-blue-500';
      default: return 'text-gray-500';
    }
  };

  const getPlatformIcon = (platform: string) => {
    return platformIcons[platform] || '🔗';
  };

  return (
    <div className="bg-gray-800 rounded-lg p-6 h-full space-y-6">
      {/* ⚡ 1-Line Connect (old plan, Feature 1): URL paste করেই MCP/AI/Webhook connect */}
      <OneLinerMCPConnect />

      <div className="flex justify-between items-center mb-6">
        <h2 className="text-xl font-bold text-cyan-400">Connected Platforms Vault</h2>
        <button
          onClick={() => setShowAddModal(true)}
          className="px-4 py-2 bg-cyan-600 hover:bg-cyan-700 rounded text-sm"
        >
          + Add Platform
        </button>
      </div>

      {loading && <p className="rounded-lg border border-dashed border-gray-600 p-6 text-sm text-gray-400">Loading connected platforms...</p>}
      {!loading && loadError && <p className="rounded-lg border border-red-500/30 p-6 text-sm text-red-300">{loadError}</p>}
      {!loading && !loadError && platforms.length === 0 && <p className="rounded-lg border border-dashed border-gray-600 p-6 text-sm text-gray-400">No platforms connected yet. Add a supported integration to get started.</p>}
      {!loading && platforms.length > 0 && <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {platforms.map((platform) => (
          <div
            key={platform.id}
            className={`border rounded-lg p-4 ${
              platform.connected
                ? 'border-green-500 bg-gray-750'
                : 'border-gray-600 bg-gray-850'
            }`}
          >
            <div className="flex justify-between items-start">
              <div className="flex items-center">
                <span className="text-2xl mr-3">{getPlatformIcon(platform.platform)}</span>
                <div>
                  <h3 className="font-semibold">{platform.name}</h3>
                  <p className="text-sm text-gray-400">{platform.platform}</p>
                </div>
              </div>
              <span className={`text-xs px-2 py-1 rounded-full ${getStatusColor(platform.status)}`}>
                {platform.status}
              </span>
            </div>

            <div className="mt-3">
              <div className="flex justify-between text-sm mb-2">
                <span className="text-gray-400">Status:</span>
                <span className={platform.connected ? 'text-green-400' : 'text-red-400'}>
                  {platform.connected ? 'Connected' : 'Disconnected'}
                </span>
              </div>
              <div className="flex justify-between text-sm mb-3">
                <span className="text-gray-400">Last Accessed:</span>
                <span>{new Date(platform.lastAccessed).toLocaleDateString()}</span>
              </div>

              <div className="text-sm mb-3">
                <div className="text-gray-400 mb-1">Permissions:</div>
                <div className="flex flex-wrap gap-1">
                  {platform.permissions.map((perm, idx) => (
                    <span key={idx} className="text-xs bg-gray-700 px-2 py-1 rounded">
                      {perm}
                    </span>
                  ))}
                </div>
              </div>
            </div>

            <div className="flex space-x-2">
              <button
                onClick={() => {
                  setSelectedPlatform(platform);
                  setShowDetails(true);
                }}
                className="flex-1 text-xs px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded"
              >
                Details
              </button>
              <button
                onClick={() => handleToggleConnection(platform.id)}
                className={`flex-1 text-xs px-2 py-1 rounded ${
                  platform.connected
                    ? 'bg-red-600 hover:bg-red-700'
                    : 'bg-green-600 hover:bg-green-700'
                }`}
              >
                {platform.connected ? 'Disconnect' : 'Connect'}
              </button>
              <button
                onClick={() => handleDelete(platform.id)}
                className="text-xs px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded"
              >
                Remove
              </button>
            </div>
          </div>
        ))}
      </div>}

      {/* Add Platform Modal */}
      {showAddModal && (
        <div className="fixed inset-0 bg-black bg-opacity-75 flex items-center justify-center z-50 p-4">
          <div className="bg-gray-800 rounded-lg w-full max-w-md">
            <div className="p-6">
              <div className="flex justify-between items-center mb-4">
                <h3 className="text-lg font-semibold text-cyan-400">Add New Platform</h3>
                <button
                  onClick={() => setShowAddModal(false)}
                  className="text-gray-400 hover:text-white"
                >
                  ✕
                </button>
              </div>

              <div className="space-y-4">
                <div>
                  <label className="block text-gray-300 mb-2">Platform Name</label>
                  <input
                    type="text"
                    value={newPlatform.name}
                    onChange={(e) => setNewPlatform({...newPlatform, name: e.target.value})}
                    className="w-full p-2 bg-gray-700 text-white rounded border border-gray-600 focus:outline-none focus:border-cyan-500"
                    placeholder="e.g., My GitHub Account"
                  />
                </div>

                <div>
                  <label className="block text-gray-300 mb-2">Platform Type</label>
                  <select
                    value={newPlatform.platform}
                    onChange={(e) => setNewPlatform({...newPlatform, platform: e.target.value})}
                    className="w-full p-2 bg-gray-700 text-white rounded border border-gray-600 focus:outline-none focus:border-cyan-500"
                  >
                    <option value="">Select a platform</option>
                    <option value="GitHub">GitHub</option>
                    <option value="GitLab">GitLab</option>
                    <option value="Google Cloud">Google Cloud</option>
                    <option value="AWS">AWS</option>
                    <option value="Azure">Azure</option>
                    <option value="DigitalOcean">DigitalOcean</option>
                    <option value="Slack" disabled>Slack (Coming soon)</option>
                    <option value="Discord">Discord</option>
                    <option value="Jira">Jira</option>
                    <option value="Notion" disabled>Notion (Coming soon)</option>
                  </select>
                </div>

                <div>
                  <label className="block text-gray-300 mb-2">Credentials</label>
                  <textarea
                    value={newPlatform.credentials}
                    onChange={(e) => setNewPlatform({...newPlatform, credentials: e.target.value})}
                    className="w-full p-2 bg-gray-700 text-white rounded border border-gray-600 focus:outline-none focus:border-cyan-500"
                    rows={3}
                    placeholder="Paste your API key, token, or credentials here"
                  />
                </div>
              </div>

              <div className="mt-6 flex justify-end space-x-2">
                <button
                  onClick={() => setShowAddModal(false)}
                  className="px-4 py-2 bg-gray-600 hover:bg-gray-700 rounded"
                >
                  Cancel
                </button>
                <button
                  onClick={handleAddPlatform}
                  disabled={!newPlatform.name || !newPlatform.platform || !newPlatform.credentials}
                  className={`px-4 py-2 rounded ${
                    !newPlatform.name || !newPlatform.platform || !newPlatform.credentials
                      ? 'bg-gray-600 cursor-not-allowed'
                      : 'bg-cyan-600 hover:bg-cyan-700'
                  }`}
                >
                  Add Platform
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Platform Details Modal */}
      {showDetails && selectedPlatform && (
        <div className="fixed inset-0 bg-black bg-opacity-75 flex items-center justify-center z-50 p-4">
          <div className="bg-gray-800 rounded-lg w-full max-w-md">
            <div className="p-6">
              <div className="flex justify-between items-center mb-4">
                <h3 className="text-lg font-semibold text-cyan-400">Platform Details</h3>
                <button
                  onClick={() => setShowDetails(false)}
                  className="text-gray-400 hover:text-white"
                >
                  ✕
                </button>
              </div>

              <div className="space-y-4">
                <div>
                  <div className="text-gray-400 text-sm">Name</div>
                  <div className="text-white">{selectedPlatform.name}</div>
                </div>

                <div>
                  <div className="text-gray-400 text-sm">Platform</div>
                  <div className="text-white">{selectedPlatform.platform}</div>
                </div>

                <div>
                  <div className="text-gray-400 text-sm">Status</div>
                  <div className={`capitalize ${getStatusColor(selectedPlatform.status)}`}>
                    {selectedPlatform.status}
                  </div>
                </div>

                <div>
                  <div className="text-gray-400 text-sm">Connection Status</div>
                  <div className={selectedPlatform.connected ? 'text-green-400' : 'text-red-400'}>
                    {selectedPlatform.connected ? 'Connected' : 'Disconnected'}
                  </div>
                </div>

                <div>
                  <div className="text-gray-400 text-sm">Last Accessed</div>
                  <div>{new Date(selectedPlatform.lastAccessed).toLocaleString()}</div>
                </div>

                <div>
                  <div className="text-gray-400 text-sm mb-2">Permissions</div>
                  <div className="flex flex-wrap gap-1">
                    {selectedPlatform.permissions.map((perm, idx) => (
                      <span key={idx} className="text-xs bg-gray-700 px-2 py-1 rounded">
                        {perm}
                      </span>
                    ))}
                  </div>
                </div>
              </div>

              <div className="mt-6 flex justify-end">
                <button
                  onClick={() => setShowDetails(false)}
                  className="px-4 py-2 bg-cyan-600 hover:bg-cyan-700 rounded"
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ConnectedPlatformsVault;
