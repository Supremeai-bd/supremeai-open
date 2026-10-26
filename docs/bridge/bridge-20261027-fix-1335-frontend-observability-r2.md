# 🌉 Bridge Work Order — [P1] Fix: honest incident text + deploy-pipeline vs service health separation (fix for #1335)

Implements the alarm-hygiene core of parent issue #1335 / bridge-20261027-frontend-observability. Patches: infrastructure/mcp-control-plane/src/health/incident.ts and engine.ts. Incidents can never read Error-colon-None again; a failed LAST deploy with a still-live service keeps the service honestly healthy with structured pipeline evidence instead of flipping overallStatus to degraded fleet-wide.
