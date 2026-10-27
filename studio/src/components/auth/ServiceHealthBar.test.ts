import { describe, it, expect } from 'vitest';
import {
  publicHealthRefetchInterval,
  HEALTH_REFETCH_INTERVAL_MS,
  HEALTH_ERROR_REFETCH_INTERVAL_MS,
} from './ServiceHealthBar';

// supremeai-studio#1 (CORS residual / failed health telemetry): while the
// backend rejects this deployment's origin (fix tracked in the monorepo,
// supremeai#205), every health cycle fails. The OLD policy stopped polling
// forever on the first error (`refetchInterval: error ? false`) — the chip
// could never recover when the backend policy landed without a manual reload.
// The exported policy function pins the self-healing contract.
describe('ServiceHealthBar polling policy (supremeai-studio#1)', () => {
  it('keeps polling at the healthy cadence when the query is live', () => {
    expect(publicHealthRefetchInterval('success')).toBe(HEALTH_REFETCH_INTERVAL_MS);
    expect(publicHealthRefetchInterval('pending')).toBe(HEALTH_REFETCH_INTERVAL_MS);
    expect(HEALTH_REFETCH_INTERVAL_MS).toBe(20_000);
  });

  it('slows down but NEVER disables polling in the error state (self-healing telemetry)', () => {
    expect(publicHealthRefetchInterval('error')).toBe(HEALTH_ERROR_REFETCH_INTERVAL_MS);
    expect(HEALTH_ERROR_REFETCH_INTERVAL_MS).toBe(60_000);
    expect(HEALTH_ERROR_REFETCH_INTERVAL_MS).toBeGreaterThan(0);
  });
});
