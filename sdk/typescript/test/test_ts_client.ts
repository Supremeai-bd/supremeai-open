import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { SupremeAIClient, GatewayError, SSEParser } from '../src/client.ts';

function createMockServer() {
  const state = {
    flakyHits: 0,
    lastAuth: '',
    lastPath: '',
    lastBody: null as any,
  };

  const server = http.createServer((req, res) => {
    state.lastAuth = req.headers['authorization'] || '';
    state.lastPath = req.url || '';

    let body = '';
    req.on('data', (chunk) => {
      body += chunk;
    });

    req.on('end', () => {
      try {
        state.lastBody = body ? JSON.parse(body) : null;
      } catch {
        state.lastBody = body;
      }

      if (req.method === 'POST' && req.url === '/v1/chat/completions') {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({
          id: 'chat_ts_123',
          choices: [{ message: { content: 'Hello from TypeScript test' }, finish_reason: 'stop' }],
        }));
      } else if (req.method === 'GET' && req.url === '/v1/models') {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({
          object: 'list',
          data: [{ id: 'llama-3.1-8b-instant', object: 'model' }],
        }));
      } else if (req.method === 'GET' && req.url === '/v1/health') {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ ok: true, version: '1.0.0' }));
      } else if (req.url === '/v1/flaky') {
        state.flakyHits++;
        if (state.flakyHits <= 2) {
          res.writeHead(503, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ error: { code: 'UPSTREAM_BUSY', message: 'try again' } }));
        } else {
          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ ok: true, attempts: state.flakyHits }));
        }
      } else if (req.url === '/v1/always-503') {
        res.writeHead(503, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: { code: 'GATEWAY_DOWN', message: 'never recovers' } }));
      } else {
        res.writeHead(404, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: { code: 'NOT_FOUND', message: 'not found' } }));
      }
    });
  });

  return { server, state };
}

test('SupremeAI TypeScript Client test suite', async (t) => {
  const { server, state } = createMockServer();

  await new Promise<void>((resolve) => {
    server.listen(0, '127.0.0.1', () => resolve());
  });

  const addr = server.address() as any;
  const baseUrl = `http://127.0.0.1:${addr.port}`;

  t.after(() => {
    server.close();
  });

  await t.test('1. Signs headers with bearer token', async () => {
    const client = new SupremeAIClient({ baseUrl, apiKey: 'test-secret-key-123' });
    const health = await client.health();
    assert.equal(health.ok, true);
    assert.equal(state.lastAuth, 'Bearer test-secret-key-123');
  });

  await t.test('2. listModels calls /v1/models', async () => {
    const client = new SupremeAIClient({ baseUrl, apiKey: 'test-key' });
    const models = await client.listModels();
    assert.equal(Array.isArray(models), false); // object with data list
    assert.equal(state.lastPath, '/v1/models');
  });

  await t.test('3. chat() posts to /v1/chat/completions', async () => {
    const client = new SupremeAIClient({ baseUrl, apiKey: 'test-key' });
    const res = await client.chat<{ id: string; choices: any[] }>({
      model: 'auto',
      messages: [{ role: 'user', content: 'hi' }],
    });
    assert.equal(res.id, 'chat_ts_123');
    assert.equal(res.choices[0].message.content, 'Hello from TypeScript test');
    assert.equal(state.lastPath, '/v1/chat/completions');
    assert.equal(state.lastBody.model, 'auto');
  });

  await t.test('4. Retries 503 with backoff and recovers', async () => {
    state.flakyHits = 0;
    const client = new SupremeAIClient({ baseUrl, apiKey: 'test-key', maxRetries: 4, backoffMs: 20 });
    const res = await client.request<any>('GET', '/v1/flaky');
    assert.equal(res.ok, true);
    assert.equal(res.attempts, 3);
  });

  await t.test('5. Terminal 503 surfaces GatewayError', async () => {
    const client = new SupremeAIClient({ baseUrl, apiKey: 'test-key', maxRetries: 2, backoffMs: 10 });
    await assert.rejects(
      async () => {
        await client.request<any>('GET', '/v1/always-503');
      },
      (err: any) => {
        assert.ok(err instanceof GatewayError);
        assert.equal(err.status, 503);
        assert.equal(err.code, 'GATEWAY_DOWN');
        assert.equal(err.retryable, true);
        return true;
      }
    );
  });

  await t.test('6. SSEParser re-assembles multiline events correctly', () => {
    const parser = new SSEParser();
    const chunk1 = 'event: token\ndata: {"type":"token","text":"He"}\n\n';
    const chunk2 = 'event: token\ndata: {"type":"token","text":"llo"}\n\nevent: done\ndata: {"type":"done","finishReason":"stop"}\n\n';

    const events1 = parser.push(chunk1);
    const events2 = parser.push(chunk2);
    const all = [...events1, ...events2];

    assert.equal(all.length, 3);
    assert.equal(all[0].event, 'token');
    assert.equal((all[0].parsed as any).text, 'He');
    assert.equal(all[1].event, 'token');
    assert.equal((all[1].parsed as any).text, 'llo');
    assert.equal(all[2].event, 'done');
    assert.equal((all[2].parsed as any).finishReason, 'stop');
  });
});
