/**
 * Cloudflare Edge Worker Module Entrypoint (infrastructure/cloudflare)
 *
 * Re-exports/delegates to the active root infrastructure/cloudflare_worker.js.
 * Preserves the canonical module boundary and operational integrity.
 */

export * from "../cloudflare_worker.js";
