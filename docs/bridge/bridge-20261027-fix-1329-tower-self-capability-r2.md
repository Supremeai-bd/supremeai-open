# 🌉 Bridge Work Order — [P0] Fix: honest audit verdicts + MCP conformance self-test (fix for #1329)

Implements part of parent issue #1329 / bridge-20261027-tower-self-capability. Patches: infrastructure/mcp-control-plane/src/tools/intelligence.tools.ts (reason capture, degraded flag, verdict INCOMPLETE in fallback mode — never PASS) and NEW scripts/ci/mcp_conformance_selftest.py (stdlib-only CI gate: every advertised resource readable, graph query returns symbols, audit never PASS in fallback). Graph-sync CI step remains a protected-path follow-up in the parent issue.
