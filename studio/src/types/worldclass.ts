export interface ProjectFile {
  path: string;
  name: string;
  language: string;
  content: string;
  icon?: string;
  isModified?: boolean;
}

export interface VersionSnapshot {
  id: string;
  version: string;
  title: string;
  timestamp: string;
  author: 'JARVIS Agent' | 'Developer';
  summary: string;
  files: Record<string, string>; // path -> content
  diffSummary: {
    added: number;
    removed: number;
    filesChanged: number;
  };
}

export interface SelectedElementInfo {
  selector: string;
  tagName: string;
  className: string;
  textContent: string;
  boundingRect: {
    top: number;
    left: number;
    width: number;
    height: number;
  };
}

export interface LiveDeploymentState {
  status: 'idle' | 'deploying' | 'live' | 'failed';
  url?: string;
  provider: 'Cloudflare Edge' | 'Vercel' | 'Render';
  deployedAt?: string;
  dnsRegion: string;
  sslStatus: 'Active (TLS 1.3)' | 'Provisioning';
  cdnHits: number;
}

export interface InjectedPackage {
  name: string;
  version: string;
  cdnUrl: string;
  installed: boolean;
  category: 'UI' | 'Animation' | 'Icons' | 'Data';
}
