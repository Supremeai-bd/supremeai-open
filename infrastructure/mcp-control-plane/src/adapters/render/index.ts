import { buildAccountRegistry } from "../../registry/account.registry.js";
import { httpRequest, bearerAuth } from "../../lib/http.js";
import { maskSecretValue } from "../../lib/masking.js";

const BASE_URL = "https://api.render.com/v1";

function getApiKey(accountId: string): string {
  const accounts = buildAccountRegistry();
  const account = accounts.find((a) => a.id === accountId && a.provider === "render");
  if (!account) throw new Error(`Render account not found: ${accountId}`);
  if (!account.available) throw new Error(`Render account is not configured/available: ${accountId}`);

  const apiKey = process.env[account.apiKeyRef];
  if (!apiKey) throw new Error(`Missing Render API Key in env for: ${account.apiKeyRef}`);
  return apiKey;
}

export async function listServices(accountId: string): Promise<unknown> {
  const apiKey = getApiKey(accountId);
  const res = await httpRequest(`${BASE_URL}/services?limit=20`, {
    headers: bearerAuth(apiKey),
  });
  return res.data;
}

export async function getServiceHealth(accountId: string, serviceId: string): Promise<unknown> {
  const apiKey = getApiKey(accountId);
  const res = await httpRequest(`${BASE_URL}/services/${serviceId}`, {
    headers: bearerAuth(apiKey),
  });
  
  // Try to fetch last deploy
  let deployStatus = "unknown";
  try {
    const deploysRes = await httpRequest(`${BASE_URL}/services/${serviceId}/deploys?limit=1`, {
      headers: bearerAuth(apiKey),
    });
    const deploys = deploysRes.data as any[];
    if (deploys && deploys.length > 0) {
      deployStatus = deploys[0].deploy.status;
    }
  } catch (err) {
    // Ignore error for deploys
  }

  return {
    service: res.data,
    lastDeployStatus: deployStatus
  };
}

export async function getDeployLogs(accountId: string, serviceId: string): Promise<unknown> {
  const apiKey = getApiKey(accountId);
  
  // First, get the latest deploy
  const deploysRes = await httpRequest(`${BASE_URL}/services/${serviceId}/deploys?limit=1`, {
    headers: bearerAuth(apiKey),
  });
  const deploys = deploysRes.data as any[];
  if (!deploys || deploys.length === 0) {
    throw new Error("No deploys found for this service");
  }

  const deployId = deploys[0].deploy.id;
  // Get logs for the deploy (note: Render deploy logs stream, but we might just fetch recent ones if they support it)
  // Render doesn't have a direct /logs endpoint in API v1 for historic deploy logs easily, it's stream based or via GraphQL.
  // Actually, they don't have a public v1 API for fetching raw historic logs, but let's try calling it if it exists, or just return the deploy info.
  return {
    message: "Deploy log fetch is not fully supported by Render v1 REST API. Returning latest deploy info.",
    latestDeploy: deploys[0].deploy
  };
}

export async function getServiceEnvVars(accountId: string, serviceId: string): Promise<unknown> {
  const apiKey = getApiKey(accountId);
  const res = await httpRequest(`${BASE_URL}/services/${serviceId}/env-vars?limit=50`, {
    headers: bearerAuth(apiKey),
  });
  // Read-Only: env var values are masked by KEY NAME *and* by VALUE SHAPE
  // (#695). URLs with embedded credentials, bcrypt/argon hashes, JWTs,
  // high-entropy hex/base64 tokens and connection strings are masked even when
  // the variable's key name does not contain key/secret/token.
  const items = res.data as any[];
  return items.map((item: any) => ({
    key: item.envVar?.key,
    value: item.envVar?.value ? maskSecretValue(String(item.envVar.key ?? ""), String(item.envVar.value)) : "",
  }));
}

