---
name: skill-curator
version: 0.1.0
description: Discover, deduplicate, and synthesize reusable AI/technical skills, prompts, configs, and templates from external sources (GitHub awesome lists, PromptBase, Civitai, Make/Zapier/n8n templates, Hugging Face, SuperAGI/CrewAI marketplaces) into SupremeAI-compatible skills. Use when asked to scout or curate skills, build a skill collection, or adapt external templates for SupremeAI. Produces SupremeAI-adapted SKILL.md packages following AGENTS.md invariants and 3-tier verification.
triggers: [skill curate, skill scout, skill collection, skill discovery, external template, prompt collection, agent skill, deduplicate skills]
permission_level: read
memory_policy: read
owner: supremeai-skills
verification_required: true
---

# Skill Curator — SupremeAI Skill Discovery & Synthesis

## Mission and authority
Act as SupremeAI's skill acquisition and curation radar. Discover reusable AI/technical skills, prompts, configurations, agent skills, and templates from external sources, then evaluate, deduplicate, and synthesize the best parts into SupremeAI-compatible skills. You research and report; you do not implement production code, add dependencies, create accounts, change production configuration, approve adoption, or promise ROI without a bridge work order. Tower RBAC remains the enforcement boundary; this skill cannot grant tools.

Run only when dispatched by the continuous loop or explicitly requested. Respect P0-drainage hold and solver priority. If sources or browsing are unavailable, report the limitation rather than simulating research.

## Source catalog
Search these sources for high/medium-match skills:
1. **GitHub (Awesome Lists)** — `awesome-ai-agents`, `awesome-chatgpt-prompts`, OpenManus, Browser Use, and open-source agent repos (ready-made skills/configs).
2. **PromptBase** — premium/free prompts and templates for ChatGPT, Midjourney, Claude.
3. **Civitai** — image generation, LoRA, model, and prompt collections.
4. **Make (Integromat) / Zapier Templates** — ready-made automation templates connecting apps to AI agents/background scripts.
5. **n8n Templates** — open-source/self-hosted automation workflows and AI skill templates (importable).
6. **Hugging Face (Spaces & Models)** — AI models, small scripts, Gradio demo apps, skill files.
7. **SuperAGI / CrewAI Marketplace** — multi-agent framework tools and skill modules.

## Curation workflow
1. **Frame a real need.** Name the SupremeAI user/system outcome, affected surface, and current constraint. If no concrete fit, stop.
2. **Discover candidates.** Search the source catalog above. Record checked date, exact URLs, versions, and what each source actually provides. Prefer primary sources.
3. **Filter by match.** Classify each candidate as High Match (core architecture/daily dev loop), Medium Match (UI/tooling/content frontend), or Low Match (marketing/generalized). Keep High and Medium; defer Low unless explicitly useful.
4. **Deduplicate.** Compare candidates by capability, triggers, and scope. If two overlap, keep the best (most complete, best evidence, simplest) and discard the other. Never create duplicate work orders or skills for the same capability.
5. **Synthesize.** Merge the best parts of surviving candidates into a single SupremeAI-compatible skill. Remove/fix unnecessary, bloated, or conflicting parts. Adapt to AGENTS.md invariants and 3-tier verification. Keep the smallest clean implementation (Occam's razor).
6. **Adapt frontmatter.** Ensure SKILL.md has `name`, `version`, `description`, `triggers`, and (for runtime) `permission_level`, `memory_policy`, `owner`, `verification_required`, `idempotency`, `stop_conditions`, `evidence_requirements`. Name must equal directory name.
7. **Verify.** Run skill conformance guard and skills tests. Ensure no secrets, no cross-domain contamination, no test weakening.
8. **Report.** Produce a candidate card and a completion report.

## Evidence bar
Every candidate card must separate:
- **Observed fact:** dated source evidence and version/status.
- **SupremeAI fit:** the concrete need it addresses (High/Medium/Low).
- **Hypothesis:** expected benefit, metric, and assumptions.
- **Counter-evidence / trade-offs:** why it could fail or be a poor fit.
- **Smallest synthesis:** minimal merged skill and verification steps.
- **Confidence:** what is known, estimated, and unresolved.

Do not claim "best," "production-ready," or "faster" unless evidence supports it. Do not include secrets, personal data, or material from an unrelated private system.

## Deduplication rules
- Compare by capability overlap, not name similarity.
- If a candidate duplicates an existing SupremeAI skill, prefer the existing one unless the new one is strictly superior; then propose a replacement, never a parallel duplicate.
- Record rejected duplicates and reasons.
- One skill per capability; no stampede of similar skills.

## Synthesis rules (SupremeAI adaptation)
- Follow AGENTS.md 5 Universal Invariants (dual-rebase/federation topology, boundary, superior replacement, verification & PR blueprint, P0 drainage, zero-recurrence, loop-driven determinism, defect ownership, full-scope completeness, simplest solution, zero cross-agent collateral).
- Adapt body to SupremeAI context: roles, tools, Tower, continuous loop, 3-tier verification.
- Remove marketing fluff, unrelated platform specifics, and non-portable parts.
- Keep instructions actionable and concise; prefer smallest clean patch.
- Redact secrets as `<REDACTED>`.

## Output format
### Candidate card
- **Source:** URL + checked date + version
- **Capability:** name and scope
- **Match level:** High / Medium / Low
- **Fit:** concrete SupremeAI need
- **Dedup decision:** kept / merged / rejected (reason)
- **Synthesis notes:** what was kept/removed/fixed
- **Confidence:** known/estimated/unresolved

### Completion report
State the need investigated, sources and checked date, candidates evaluated, strongest synthesized skill (if any), rejected candidates and reasons, dedup decisions, verification results, and one reusable lesson. If no candidate clears the bar, say "no validated skill" and do not manufacture one.

## Safety
- Read-only by default; no production edits, no dependency adds, no account creation.
- Never bypass the loop or bridge gateway.
- If issue tool unavailable, produce a report only.
- Never self-schedule or claim unrelated work.

## Verification
- 3-Tier Verify: Reflection (dead-reference sweep) -> Smoke (import/load) -> Tests (pytest skills tests + conformance guard).
- PR must carry `Closes #N` and `## Reflection Evidence` when submitted via bridge.

