export type CapabilityStatus = 'ready' | 'idle' | 'unavailable' | 'pending' | 'requestable';

export interface UserCapability {
  id: string;
  label: string;
  description: string;
  status: CapabilityStatus;
  connectionId?: string;
  href?: string;
}

export interface AccessContext {
  id: string;
  label: string;
  role: 'user' | 'workspace_admin' | 'tenant_admin' | 'admin';
  authorized: boolean;
}

export interface ConnectionContract {
  id: string;
  name: string;
  type: 'mcp' | 'oauth' | 'rest' | 'github' | 'unknown';
  status: 'connected' | 'pending' | 'unavailable' | 'paused';
  capabilities: UserCapability[];
}

export interface UnavailableCapability {
  label: string;
  reason: string;
  requestable?: boolean;
}

export type AddIntent = 'service' | 'automation' | 'tool' | 'storage';

export const ADD_INTENTS: Array<{ id: AddIntent; label: string; description: string }> = [
  { id: 'service', label: 'Connect a service', description: 'Use a service you already rely on.' },
  { id: 'automation', label: 'Create an automation', description: 'Turn a repeated task into a helper.' },
  { id: 'tool', label: 'Add a custom tool', description: 'Connect a tool from a secure URL.' },
  { id: 'storage', label: 'Add file access', description: 'Bring documents and cloud files into your work.' },
];

export function capabilityFromModule(module: { id: string; label: string; description: string; href: string }): UserCapability {
  return { id: module.id, label: module.label, description: module.description, status: 'ready', href: module.href };
}

export function explainUnavailable(label: string): UnavailableCapability {
  return { label, reason: 'Your workspace does not currently grant access to this capability.', requestable: true };
}

export type { UserCapability as default };
