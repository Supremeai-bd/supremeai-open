import React, { useState } from 'react';
import { usePlugins, type PluginManifest } from '../../../hooks/usePlugins';
import { PluginCard } from './PluginCard';
import { InstallModal } from './InstallModal';

export const PluginMarketplace: React.FC = () => {
    const { marketplacePlugins, installedPlugins, loading, error, installPlugin, uninstallPlugin } = usePlugins();
    const [selectedPlugin, setSelectedPlugin] = useState<PluginManifest | null>(null);
    const [isModalOpen, setIsModalOpen] = useState(false);

    if (loading) return <div className="p-8 text-center text-gray-500">Loading Marketplace...</div>;
    if (error) return <div className="p-8 text-center text-red-500">Error: {error}</div>;

    const handleInstallClick = (plugin: PluginManifest) => {
        setSelectedPlugin(plugin);
        setIsModalOpen(true);
    };

    const handleConfirmInstall = async (capabilities: string[]) => {
        if (selectedPlugin) {
            await installPlugin(selectedPlugin.id, capabilities);
            setIsModalOpen(false);
            setSelectedPlugin(null);
        }
    };

    return (
        <div className="p-8 max-w-7xl mx-auto">
            <h1 className="text-3xl font-bold mb-8">Plugin Marketplace</h1>
            
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {marketplacePlugins.map((plugin) => {
                    const isInstalled = installedPlugins.some(p => p.plugin_id === plugin.id);
                    return (
                        <PluginCard 
                            key={plugin.id}
                            plugin={plugin}
                            isInstalled={isInstalled}
                            onInstall={() => handleInstallClick(plugin)}
                            onUninstall={() => uninstallPlugin(plugin.id)}
                        />
                    );
                })}
            </div>

            {selectedPlugin && (
                <InstallModal 
                    isOpen={isModalOpen}
                    onClose={() => setIsModalOpen(false)}
                    plugin={selectedPlugin}
                    onConfirm={handleConfirmInstall}
                />
            )}
        </div>
    );
};
