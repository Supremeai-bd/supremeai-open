import React from 'react';
import type { PluginManifest } from '../../../hooks/usePlugins';

interface Props {
    plugin: PluginManifest;
    isInstalled: boolean;
    onInstall: () => void;
    onUninstall: () => void;
}

export const PluginCard: React.FC<Props> = ({ plugin, isInstalled, onInstall, onUninstall }) => {
    return (
        <div className="border border-gray-200 rounded-xl p-6 flex flex-col items-start bg-white shadow-sm hover:shadow-md transition-shadow">
            <div className="flex items-center gap-4 mb-4">
                <img src={plugin.icon_url} alt={plugin.name} className="w-12 h-12 rounded object-cover bg-gray-50 p-1" />
                <div>
                    <h3 className="font-semibold text-lg">{plugin.name}</h3>
                    <span className="text-xs bg-blue-100 text-blue-700 px-2 py-1 rounded-full uppercase tracking-wider">
                        {plugin.source}
                    </span>
                </div>
            </div>
            
            <p className="text-gray-600 text-sm mb-6 flex-grow">{plugin.description}</p>
            
            <div className="w-full flex justify-between items-center mt-auto border-t pt-4 border-gray-100">
                <span className="text-xs text-gray-400 capitalize">{plugin.category}</span>
                {isInstalled ? (
                    <button 
                        onClick={onUninstall}
                        className="px-4 py-2 border border-red-200 text-red-600 hover:bg-red-50 rounded-lg text-sm font-medium transition-colors"
                    >
                        Uninstall
                    </button>
                ) : (
                    <button 
                        onClick={onInstall}
                        className="px-4 py-2 bg-black text-white hover:bg-gray-800 rounded-lg text-sm font-medium transition-colors"
                    >
                        Install
                    </button>
                )}
            </div>
        </div>
    );
};
