import { Resource } from "../registry/resource.registry.js";

export interface ProviderAdapter {
  provider: string;
  discover(): Promise<Resource[]>;
  getStatus(resourceId: string): Promise<unknown>;
}
