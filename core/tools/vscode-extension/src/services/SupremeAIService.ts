import { SupremeAIService } from '@supremeai/shared-services';
import { SupremeAIConfig } from '../types';

let supremeAIService: SupremeAIService | null = null;

export { SupremeAIService };

export function getSupremeAIService(config?: SupremeAIConfig): SupremeAIService {
  // Expecting extension.ts to initialize this with platform adapters
  if (!supremeAIService) {
    throw new Error('SupremeAIService not initialized.');
  }
  return supremeAIService;
}

export function setSupremeAIService(service: SupremeAIService): void {
  supremeAIService = service;
}
