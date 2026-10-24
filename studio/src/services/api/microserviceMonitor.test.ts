import { describe, it, expect } from 'vitest';

const { fetchJavaWorkerHealth } = await import('./microserviceMonitor');

const offline = {
  status: 'OFFLINE',
  uptimeSeconds: 0,
  activeTasks: 0,
  queuedTasks: 0,
  memoryUsageMb: 0,
  cpuLoadPercentage: 0,
  totalTasksProcessed: 0,
};

// Issue #2475: /admin/microservices/java-worker/health backend-এ নেই — সার্ভিসটি
// এখন নেটওয়ার্ক কল না করে সরাসরি OFFLINE ফেরায়।
describe('fetchJavaWorkerHealth', () => {
  it('returns OFFLINE synchronously — no dead endpoint call', async () => {
    const res = await fetchJavaWorkerHealth();
    expect(res).toEqual(offline);
  });

  it('returns a fresh, non-shared object each call (no caller mutation leaks)', async () => {
    const a = await fetchJavaWorkerHealth();
    const b = await fetchJavaWorkerHealth();
    expect(a).not.toBe(b);
    expect(a).toEqual(b);
  });
});
