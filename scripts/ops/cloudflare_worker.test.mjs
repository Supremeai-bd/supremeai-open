import { createServer } from 'node:http';
import path from 'path';
import { Miniflare } from 'miniflare';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

describe('Cloudflare Worker Circuit Breaker E2E Test', () => {
    let mf;
    let server;
    let backendState;

    beforeEach(async () => {
        backendState = { isHealthy: true };

        server = createServer((req, res) => {
            if (req.url === '/health' || req.url === '/api/v1/health') {
                res.writeHead(backendState.isHealthy ? 200 : 503);
                res.end(backendState.isHealthy ? 'OK' : 'Service Unavailable');
                return;
            }

            res.writeHead(backendState.isHealthy ? 200 : 503);
            res.end(backendState.isHealthy ? 'Backend Response OK' : 'Backend Down');
        });

        await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));

        const address = server.address();
        const baseUrl = typeof address === 'object' && address ? `http://127.0.0.1:${address.port}` : 'http://127.0.0.1:3000';
        const workerScriptPath = path.resolve(process.cwd(), 'infrastructure/cloudflare_worker.js');

        mf = new Miniflare({
            scriptPath: workerScriptPath,
            kvNamespaces: ['SUPREMEAI_KV'],
            bindings: {
                GCP_CLOUD_RUN_URL: baseUrl,
                GCP_WEIGHT: '100',
            },
        });
    });

    afterEach(async () => {
        if (server) {
            await new Promise((resolve, reject) => {
                server.close((error) => (error ? reject(error) : resolve()));
            });
        }
    });

    it('ব্যাকএন্ড সুস্থ থাকলে সফলভাবে রিকোয়েস্ট ফরওয়ার্ড করবে', async () => {
        backendState.isHealthy = true;
        const res = await mf.dispatchFetch('http://localhost:8787/');
        expect(res.status).toBe(200);
        const text = await res.text();
        expect(text).toBe('Backend Response OK');
    });

    it('টানা ৩ বার হেলথ চেক ফেইল হলে সার্কিট ব্রেকার ট্রিপ করবে এবং 503 রেসপন্স দেবে', async () => {
        backendState.isHealthy = false;
        const kv = await mf.getKVNamespace('SUPREMEAI_KV');
        await kv.delete('healthy_backends');

        let res = await mf.dispatchFetch('http://localhost:8787/');
        expect(res.status).toBe(503);
        expect(await res.text()).toBe('Backend Down');

        res = await mf.dispatchFetch('http://localhost:8787/');
        expect(res.status).toBe(503);
        expect(await res.text()).toBe('Backend Down');

        res = await mf.dispatchFetch('http://localhost:8787/');
        expect(res.status).toBe(503);
        expect(await res.text()).toBe('Backend Down');

        res = await mf.dispatchFetch('http://localhost:8787/');
        expect(res.status).toBe(503);
        expect(await res.text()).toContain('SupremeAI Core Offline');
    });

    it('সার্কিট ব্রেকার ট্রিপ করার পরও একাধিক রিকোয়েস্টে নিরাপদ 503 ফেরত দেবে', async () => {
        backendState.isHealthy = false;
        const kv = await mf.getKVNamespace('SUPREMEAI_KV');
        await kv.delete('healthy_backends');

        for (let i = 0; i < 3; i++) {
            const res = await mf.dispatchFetch('http://localhost:8787/');
            expect(res.status).toBe(503);
        }

        const res = await mf.dispatchFetch('http://localhost:8787/');
        expect(res.status).toBe(503);
        expect(await res.text()).toContain('SupremeAI Core Offline');
    });
});
