import { env } from "../../lib/env.js";
import { httpRequest, bearerAuth } from "../../lib/http.js";

const INFISICAL_URL = "https://app.infisical.com";

async function getAccessToken(): Promise<string> {
  const { clientId, clientSecret } = env.infisical;
  if (!clientId || !clientSecret) {
    throw new Error("Missing INFISICAL_CLIENT_ID or INFISICAL_CLIENT_SECRET");
  }

  const res = await httpRequest(`${INFISICAL_URL}/api/v1/auth/universal-auth/login`, {
    method: "POST",
    body: {
      clientId,
      clientSecret,
    },
  });

  const data = res.data as any;
  if (data.accessToken) {
    return data.accessToken;
  }
  throw new Error("Failed to get Infisical access token");
}

/**
 * Distinguishes the two Infisical API surfaces (issue #700 / #434):
 *  - RAW path (`/api/v3/secrets/raw`): the interface production backends use.
 *    Healthy for the machine identity — 174 prod secrets read/write verified
 *    2026-09-19 (see docs/security/INFISICAL_IDENTITY_SCOPE.md).
 *  - STANDARD encrypted path (`/api/v3/secrets`): known vendor blind-index
 *    defect returns 0 rows (issue #434). Probed in parallel and reported in a
 *    DISTINCT `standardPath` field so the vendor fix becomes visible the
 *    moment it lands — without polluting the raw-path health signal.
 */
function describeError(reason: unknown): string {
  return (reason as Error)?.message || String(reason);
}

function standardPathResult(settled: PromiseSettledResult<any>): Record<string, unknown> {
  if (settled.status === "rejected") {
    return {
      status: "error",
      count: 0,
      message: `standard encrypted list failed: ${describeError(settled.reason)}`,
      trackedBy: "issue #434",
    };
  }
  const data = (settled.value as any)?.data as any;
  const count = Array.isArray(data?.secrets) ? data.secrets.length : 0;
  if (count > 0) {
    return {
      status: "ok",
      count,
      message: "standard encrypted list serving secrets — vendor blind-index fixed; re-run parity and retire the raw-path workaround deliberately (issue #434 acceptance)",
    };
  }
  return {
    status: "empty",
    count: 0,
    message: "standard encrypted list returned 0 secrets — known vendor blind-index defect; the raw path is authoritative",
    trackedBy: "issue #434",
  };
}

export async function auditSecrets(): Promise<unknown> {
  const { projectId, environment } = env.infisical;
  if (!projectId) {
    throw new Error("Missing INFISICAL_PROJECT_ID");
  }

  const envSlug = !environment || environment === "production" ? "prod" : environment;

  let token: string;
  try {
    token = await getAccessToken();
  } catch (e) {
    return {
      status: "down",
      path: "universal-auth",
      message: `Infisical auth error: ${(e as Error).message}`,
    };
  }

  // Both probes run in parallel (with retries disabled) so the whole audit
  // stays inside the health engine's 15s sweep budget (health/engine.ts).
  const [rawSettled, standardSettled] = await Promise.allSettled([
    httpRequest(`${INFISICAL_URL}/api/v3/secrets/raw?workspaceId=${projectId}&environment=${envSlug}&secretPath=/`, {
      headers: bearerAuth(token),
      timeoutMs: 10000,
      retries: 0,
    }),
    httpRequest(`${INFISICAL_URL}/api/v3/secrets?workspaceId=${projectId}&environment=${envSlug}&secretPath=/`, {
      headers: bearerAuth(token),
      timeoutMs: 10000,
      retries: 0,
    }),
  ]);

  // Raw path is the authoritative signal: "down" only when IT fails.
  if (rawSettled.status === "rejected") {
    return {
      status: "down",
      path: "raw",
      message: `Infisical raw-path error: ${describeError(rawSettled.reason)}`,
      standardPath: standardPathResult(standardSettled),
    };
  }

  const raw = (rawSettled.value as any)?.data as any;
  const rawSecrets = Array.isArray(raw?.secrets) ? raw.secrets : [];
  const rawList = rawSecrets.map((s: any) => ({
    id: s._id,
    secretKey: s.secretKey,
    version: s.version,
    createdAt: s.createdAt,
  }));

  return {
    status: rawList.length > 0 ? "healthy" : "degraded",
    path: "raw",
    rawCount: rawList.length,
    // Metadata only — secret values are never surfaced through health/tools.
    secrets: rawList,
    standardPath: standardPathResult(standardSettled),
  };
}

/**
 * Lists Infisical workspace integrations (e.g. Render/framework secret syncs).
 * Verified 2026-09-19 (issue #700): the integrations list is EMPTY — no
 * secret-sync integrations are configured; secrets reach services via the
 * machine identity (raw path) instead. An empty list is the expected state.
 * See docs/security/INFISICAL_IDENTITY_SCOPE.md.
 */
export async function getSyncStatus(): Promise<unknown> {
  const { projectId } = env.infisical;
  const token = await getAccessToken();

  try {
    const res = await httpRequest(`${INFISICAL_URL}/api/v1/workspace/${projectId}/integrations`, {
      headers: bearerAuth(token),
      timeoutMs: 15000,
    });

    return res.data;
  } catch (e) {
    return {
      status: "error",
      message: `Infisical API Error: ${(e as Error).message}`
    };
  }
}

/**
 * Dynamically loads production secrets from Infisical and populates process.env.
 * Does not overwrite existing environment variables.
 */
export async function pullSecretsIntoProcessEnv(): Promise<{ loaded: number; skipped: boolean }> {
  const { clientId, clientSecret, projectId, environment } = env.infisical;
  if (!clientId || !clientSecret || !projectId) {
    return { loaded: 0, skipped: true };
  }

  try {
    const token = await getAccessToken();
    const envSlug = environment === "production" ? "prod" : environment;
    const res = await httpRequest(
      `${INFISICAL_URL}/api/v3/secrets/raw?workspaceId=${projectId}&environment=${envSlug}&secretPath=/`,
      {
        headers: bearerAuth(token),
        timeoutMs: 20000,
      }
    );

    const data = res.data as { secrets?: Array<{ secretKey: string; secretValue: string }> };
    const secrets = data.secrets || [];
    let count = 0;

    for (const secret of secrets) {
      if (secret.secretKey && !process.env[secret.secretKey]) {
        process.env[secret.secretKey] = secret.secretValue;
        count++;
      }
    }

    return { loaded: count, skipped: false };
  } catch (err: any) {
    console.warn(`[Infisical] Warning: unable to auto-load secrets: ${err?.message || err}`);
    return { loaded: 0, skipped: true };
  }
}

