import React, { useState } from 'react';
import type { PluginManifest } from '../../../hooks/usePlugins';

interface Props {
    isOpen: boolean;
    onClose: () => void;
    plugin: PluginManifest;
    onConfirm: (capabilities: string[]) => void;
}

export const InstallModal: React.FC<Props> = ({ isOpen, onClose, plugin, onConfirm }) => {
    const [selectedCaps, _setSelectedCaps] = useState<string[]>(['*']); // Default all for V1 simplicity

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
            <div className="bg-white rounded-2xl w-full max-w-md p-6">
                <div className="flex items-center gap-3 mb-6">
                    <img src={plugin.icon_url} alt={plugin.name} className="w-10 h-10 rounded" />
                    <h2 className="text-xl font-bold">Install {plugin.name}</h2>
                </div>
                
                <p className="text-gray-600 mb-6">
                    This plugin requires access to certain capabilities. Do you want to proceed with the installation?
                </p>

                <div className="bg-gray-50 rounded-lg p-4 mb-6">
                    <h4 className="text-sm font-semibold mb-2">Requested Permissions</h4>
                    <ul className="text-sm text-gray-600 list-disc list-inside">
                        <li>Full Agent Access (all available tools for this plugin)</li>
                    </ul>
                </div>

                <div className="flex justify-end gap-3">
                    <button 
                        onClick={onClose}
                        className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-lg font-medium"
                    >
                        Cancel
                    </button>
                    <button 
                        onClick={() => onConfirm(selectedCaps)}
                        className="px-4 py-2 bg-black text-white hover:bg-gray-800 rounded-lg font-medium"
                    >
                        Confirm Install
                    </button>
                </div>
            </div>
        </div>
    );
};
