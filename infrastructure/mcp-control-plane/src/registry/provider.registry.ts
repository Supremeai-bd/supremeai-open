/**
 * Provider Registry — the catalog of supported providers.
 * Defines metadata about each provider (e.g. Render, GitHub) independently of user accounts.
 */

export type ProviderName =
  | "render"
  | "github"
  | "supabase"
  | "redis"
  | "cloudflare"
  | "infisical"
  | "firebase"
  | "ai"
  | "kaggle"
  | "stripe"
  | "qdrant"
  | "vercel"
  | "firecrawl"
  | "telegram"
  | "discord"
  | "whatsapp";

export interface ProviderDefinition {
  name: ProviderName;
  displayName: string;
  description: string;
  authType: "api_key" | "oauth" | "service_account" | "none";
}

export const PROVIDERS: Record<ProviderName, ProviderDefinition> = {
  render: {
    name: "render",
    displayName: "Render",
    description: "Cloud hosting provider for web services and cron jobs",
    authType: "api_key",
  },
  github: {
    name: "github",
    displayName: "GitHub",
    description: "Source control, Actions CI/CD, and issues",
    authType: "api_key",
  },
  supabase: {
    name: "supabase",
    displayName: "Supabase",
    description: "Postgres database and Auth",
    authType: "api_key",
  },
  redis: {
    name: "redis",
    displayName: "Upstash Redis",
    description: "Serverless Redis cache and queue",
    authType: "api_key",
  },
  cloudflare: {
    name: "cloudflare",
    displayName: "Cloudflare",
    description: "DNS, CDN, and Workers",
    authType: "api_key",
  },
  infisical: {
    name: "infisical",
    displayName: "Infisical",
    description: "Secret Management Platform",
    authType: "service_account",
  },
  firebase: {
    name: "firebase",
    displayName: "Firebase",
    description: "Google Firebase Auth and Storage",
    authType: "service_account",
  },
  ai: {
    name: "ai",
    displayName: "AI Providers",
    description: "LLM Inference endpoints (OpenAI, Gemini, Anthropic, DeepSeek)",
    authType: "api_key",
  },
  kaggle: {
    name: "kaggle",
    displayName: "Kaggle",
    description: "Data science notebooks and datasets",
    authType: "api_key",
  },
  stripe: {
    name: "stripe",
    displayName: "Stripe",
    description: "Payments and billing",
    authType: "api_key",
  },
  qdrant: {
    name: "qdrant",
    displayName: "Qdrant",
    description: "Vector Database",
    authType: "api_key",
  },
  vercel: {
    name: "vercel",
    displayName: "Vercel",
    description: "Frontend cloud and Edge functions",
    authType: "api_key",
  },
  firecrawl: {
    name: "firecrawl",
    displayName: "Firecrawl",
    description: "Web scraping API",
    authType: "api_key",
  },
  telegram: {
    name: "telegram",
    displayName: "Telegram",
    description: "Messaging and alerts",
    authType: "api_key",
  },
  discord: {
    name: "discord",
    displayName: "Discord",
    description: "Messaging webhooks",
    authType: "api_key",
  },
  whatsapp: {
    name: "whatsapp",
    displayName: "WhatsApp",
    description: "Messaging and alerts via WhatsApp Cloud API or Webhook Gateway",
    authType: "api_key",
  },
};
