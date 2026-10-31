---
name: mcp-tower-operator
description: Discover and operate approved tools and services through capability contracts.
triggers: [mcp tower, tool discovery, service health, provider status]
permission_level: read
memory_policy: read
owner: supremeai-skills
verification_required: true
evidence_requirements: [tool name, health status, provenance]
idempotency: read-only discovery
stop_conditions: [unauthorized tool, destructive action without approval]
---

# MCP Tower Operator

## Purpose
Discover and operate approved tools/services through capability contracts.

## Capabilities
Service health, tool discovery, provider status, permitted diagnostics, approved operational actions, and clear failure reporting.

## Safety
Separate read, write, deploy, restart, and secret-management permissions. Destructive actions need explicit policy/approval.

## Existing implementation
`infrastructure/mcp-control-plane` (tool registry, policy engine, health engine). This skill provides the reusable procedure and metadata contract.