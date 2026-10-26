export interface WorkspaceSettings {
  theme?: string;
  autoSave?: boolean;
  [key: string]: any;
}

export const useWorkspaceSettingsStore = () => {
  return {
    settings: { theme: 'dark', autoSave: true },
    updateSettings: (newSettings: Partial<WorkspaceSettings>) => {},
  };
};
export default useWorkspaceSettingsStore;
