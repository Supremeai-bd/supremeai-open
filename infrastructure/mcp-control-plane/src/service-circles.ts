import { redactSecretsInText } from "./lib/masking.js";

export type ServiceCircle = "ai" | "infrastructure" | "data" | "security" | "integration";
export type ServiceState = "registered" | "configured" | "authenticated" | "reachable" | "healthy" | "degraded" | "disabled";

export interface ServiceDescriptor {
  provider: string;
  circle: ServiceCircle;
  requiredEnv: string[];
  state: ServiceState;
  configured: boolean;
  diagnostic?: string;
}

export const serviceDescriptors: Array<Pick<ServiceDescriptor, "provider" | "circle" | "requiredEnv">> = [
  { provider: "gateway", circle: "ai", requiredEnv: ["SUPREMEAI_API_KEY"] },
  { provider: "render", circle: "infrastructure", requiredEnv: ["RENDER_API_KEY"] },
  { provider: "cloudflare", circle: "infrastructure", requiredEnv: ["CLOUDFLARE_API_TOKEN"] },
  { provider: "redis", circle: "infrastructure", requiredEnv: ["UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_TOKEN"] },
  { provider: "supabase", circle: "data", requiredEnv: ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"] },
  { provider: "qdrant", circle: "data", requiredEnv: ["QDRANT_URL"] },
  { provider: "infisical", circle: "security", requiredEnv: ["INFISICAL_PROJECT_ID"] },
  { provider: "firebase", circle: "security", requiredEnv: ["FIREBASE_SERVICE_ACCOUNT_JSON"] },
  { provider: "github", circle: "integration", requiredEnv: ["GITHUB_TOKEN"] },
  { provider: "telegram", circle: "integration", requiredEnv: ["TELEGRAM_BOT_TOKEN"] },
  { provider: "whatsapp", circle: "integration", requiredEnv: ["WHATSAPP_ACCESS_TOKEN"] },
  { provider: "stripe", circle: "integration", requiredEnv: ["STRIPE_SECRET_KEY"] },
];

export function getServiceDescriptors(): ServiceDescriptor[] {
  return serviceDescriptors.map((descriptor) => {
    const configured = descriptor.requiredEnv.every((name) => Boolean(process.env[name]));
    return {
      ...descriptor,
      configured,
      state: configured ? "configured" : "registered",
      diagnostic: configured ? undefined : "required configuration is not available",
    };
  });
}

// #117: diagnostics must carry the SAME redaction guarantee as the rest of the
// tower. This used to be a parallel key-name-only inline regex that let
// value-shaped secrets (sk-… tokens, database URLs with credentials, JWTs,
// provider tokens under innocent key names) pass through UNMASKED while the
// SSOT in src/lib/masking.ts caught them — two redactors = silent divergence.
// Delegation keeps the exported signature and the non-secret behavior
// (String(value ?? "unknown")) identical; redaction strength now matches the
// SSOT fail-closed direction: worst case a benign fragment is masked, never
// that a credential leaks.
export function redactDiagnostic(value: unknown): string {
  return redactSecretsInText(String(value ?? "unknown"));
}

export function getServiceDescriptor(provider: string): ServiceDescriptor | undefined {
  return getServiceDescriptors().find((descriptor) => descriptor.provider === provider);
}
