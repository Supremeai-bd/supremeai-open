import { Database, Activity, Cloud, GitBranch, FileText, Monitor } from 'lucide-react';

import type { Bookmark } from './types';
import { getApiBaseUrl } from '../../../utils/api';  // roadmap 1.5 (#1180)

// ════════════════════════════════════════════════════════════════════
// DEFAULT BOOKMARKS (SupremeAI Services)
// ════════════════════════════════════════════════════════════════════

export const DEFAULT_BOOKMARKS: Bookmark[] = [
  { id: 'b2', url: getApiBaseUrl(), title: 'Main Backend', category: 'service', icon: <Database size={12} /> },  // roadmap 1.5 (#1180)
  { id: 'b4', url: 'https://dash.cloudflare.com', title: 'Cloudflare Dashboard', category: 'tool', icon: <Cloud size={12} /> },
  { id: 'b5', url: 'https://dashboard.render.com', title: 'Render Dashboard', category: 'tool', icon: <Monitor size={12} /> },
  { id: 'b6', url: 'https://github.com/SaifulHaqueNiloy/supremeai', title: 'GitHub Repository', category: 'tool', icon: <GitBranch size={12} /> },
  { id: 'b7', url: 'https://supabase.com/dashboard', title: 'Supabase Console', category: 'service', icon: <Database size={12} /> },
  { id: 'b8', url: 'https://console.upstash.com', title: 'Upstash Redis', category: 'service', icon: <Database size={12} /> },
  { id: 'b9', url: 'https://docs.supremeai.dev', title: 'Documentation', category: 'doc', icon: <FileText size={12} /> },
  { id: 'b10', url: 'https://status.supremeai.dev', title: 'Status Page', category: 'service', icon: <Activity size={12} /> },
];
