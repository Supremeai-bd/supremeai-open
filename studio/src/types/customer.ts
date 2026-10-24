export interface UserProfile {
  id: string;
  username: string;
  email: string;
  role: 'viewer' | 'operator' | 'developer' | 'admin' | 'god';
  avatar_url?: string;
  preferences: UserPreferences;
  created_at: string;
  last_login: string;
}

export interface UserPreferences {
  theme: 'dark' | 'light';
  sidebar_collapsed: boolean;
  default_project_id?: string;
  notification_enabled: boolean;
  sound_enabled: boolean;
  compact_mode: boolean;
  font_size: 'small' | 'medium' | 'large';
}

export interface Project {
  id: string;
  name: string;
  description: string;
  created_at: string;
  updated_at: string;
  owner_id: string;
  settings: ProjectSettings;
}

export interface ProjectSettings {
  default_model: string;
  system_prompt: string;
  temperature: number;
  max_tokens: number;
  rag_enabled: boolean;
}

export interface Widget {
  id: string;
  type: 'chat' | 'metrics' | 'history' | 'skills' | 'files' | 'preview';
  title: string;
  position: { x: number; y: number; w: number; h: number };
  settings: Record<string, unknown>;
}

import type { UnifiedChatMessage } from './chat';

export type ChatMessage = UnifiedChatMessage;

export interface CustomerState {
  user: UserProfile | null;
  projects: Project[];
  activeProjectId: string | null;
  chatHistory: ChatMessage[];
  widgets: Widget[];
  sidebarCollapsed: boolean;
  isLoading: boolean;

  setUser: (user: UserProfile | null) => void;
  setProjects: (projects: Project[]) => void;
  setActiveProject: (id: string | null) => void;
  addMessage: (message: ChatMessage) => void;
  clearChat: () => void;
  toggleSidebar: () => void;
  reorderWidgets: (widgets: Widget[]) => void;
}
