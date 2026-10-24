import { useState, useCallback, useEffect } from 'react';
import { apiClient } from '../services/apiClient';

export interface PluginManifest {
    id: string;
    name: string;
    description: string;
    icon_url: string;
    category: string;
    source: string;
    auth_type: string;
}

export interface UserPluginInstallation {
    id: string;
    plugin_id: string;
    status: string;
    is_enabled: boolean;
}

export const usePlugins = () => {
    const [marketplacePlugins, setMarketplacePlugins] = useState<PluginManifest[]>([]);
    const [installedPlugins, setInstalledPlugins] = useState<UserPluginInstallation[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const fetchPlugins = useCallback(async () => {
        try {
            setLoading(true);
            
            // Issue #2522: raw fetch -> apiClient.get — auth/timeout/queue অটোমেটিক,
            // non-ok হলে ApiError throw (optional-endpoint silent skip আর নেই — সচ্ছতা)।
            const [marketData, installedData] = await Promise.all([
                apiClient.get<{ plugins?: PluginManifest[] }>('/api/v1/plugins/marketplace'),
                apiClient.get<{ installations?: UserPluginInstallation[] }>('/api/v1/plugins/installed'),
            ]);
            setMarketplacePlugins(marketData.plugins || []);
            setInstalledPlugins(installedData.installations || []);
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : String(err));
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchPlugins();
    }, [fetchPlugins]);

    const installPlugin = async (pluginId: string, capabilities: string[]) => {
        try {
            // Issue #2522: raw fetch -> apiClient.post।
            await apiClient.post('/api/v1/plugins/install', { plugin_id: pluginId, granted_capabilities: capabilities });
            await fetchPlugins();
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : String(err));
            throw err;
        }
    };

    const uninstallPlugin = async (pluginId: string) => {
        try {
            // Issue #2522: raw fetch -> apiClient.delete।
            await apiClient.delete(`/api/v1/plugins/uninstall/${pluginId}`);
            await fetchPlugins();
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : String(err));
            throw err;
        }
    };

    return {
        marketplacePlugins,
        installedPlugins,
        loading,
        error,
        installPlugin,
        uninstallPlugin,
        refresh: fetchPlugins
    };
};
