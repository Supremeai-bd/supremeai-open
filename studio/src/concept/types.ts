export type ViewKey = 'overview' | 'studio' | 'vscode' | 'devices';
export type DeviceKey = 'web' | 'mobile' | 'desktop';

export type NavigationItem = {
  id: ViewKey;
  label: string;
  hint: string;
};
