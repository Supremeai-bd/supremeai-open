import { useState, useCallback, useEffect } from 'react';
import { getApiBaseUrl } from '../utils/api';
import { getAuthHeaders } from '../services/apiClient';

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
            
            const baseUrl = getApiBaseUrl();
            const authHeaders = await getAuthHeaders();
            const [marketRes, installedRes] = await Promise.all([
                fetch(`${baseUrl}/api/v1/plugins/marketplace`, { headers: authHeaders }),
                fetch(`${baseUrl}/api/v1/plugins/installed`, { headers: authHeaders })
            ]);
            
            if (marketRes.ok) {
                const data = await marketRes.json();
                setMarketplacePlugins(data.plugins || []);
            }
            if (installedRes.ok) {
                const data = await installedRes.json();
                setInstalledPlugins(data.installations || []);
            }
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
            const res = await fetch(`${getApiBaseUrl()}/api/v1/plugins/install`, {
                method: 'POST',
                headers: {
                    ...(await getAuthHeaders()),
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ plugin_id: pluginId, granted_capabilities: capabilities })
            });
            if (!res.ok) throw new Error('Failed to install plugin');
            await fetchPlugins();
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : String(err));
            throw err;
        }
    };

    const uninstallPlugin = async (pluginId: string) => {
        try {
            const res = await fetch(`${getApiBaseUrl()}/api/v1/plugins/uninstall/${pluginId}`, {
                method: 'DELETE',
                headers: await getAuthHeaders(),
            });
            if (!res.ok) throw new Error('Failed to uninstall plugin');
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
