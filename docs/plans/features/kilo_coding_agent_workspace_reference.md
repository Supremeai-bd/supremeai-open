---
target_scope: supremeai_internal
# [V5 audit 2026-09-17] Legacy doc migrated to canonical governance schema; defaults are conservative (historical/derived role) — refine on next lifecycle review.
id: auto:kilo_coding_agent_workspace_reference
subject: 📁 `.kilo` ফোল্ডার — সম্পূর্ণ ব্যাখ্যা
document_role: implementation
planning_authority: Architecture Governance / Planning Circle
status: historical

---

# 📁 `.kilo` ফোল্ডার — সম্পূর্ণ ব্যাখ্যা

`.kilo` হলো **Kilo AI** ([kilo.ai](https://kilo.ai)) নামের একটি AI Coding Agent-এর কনফিগারেশন ও ওয়ার্কস্পেস ফোল্ডার।  
এটা Antigravity-র মতোই একটি AI coding assistant, যেটা SupremeAI প্রজেক্টে actively কাজ করেছে।

---

## 🗂️ ফোল্ডার স্ট্রাকচার ও প্রতিটির কাজ

| ফাইল/ফোল্ডার | কাজ |
|---|---|
| `kilo.jsonc` | Kilo-র রুট কনফিগ। `snapshot: false` মানে auto-snapshot বন্ধ। |
| `agent-manager.json` | Agent session ও worktree ম্যানেজমেন্ট ট্র্যাকার। |
| `agent/config.json` | **MCP Servers কনফিগ** — Kilo কোন কোন টুল ব্যবহার করতে পারবে। |
| `mcp/README.md` | Custom MCP সার্ভারগুলোর ডকুমেন্টেশন। |
| `plans/` | Kilo-র তৈরি করা **Implementation Plans** (১০টি)। |
| `worktrees/dirt-octopus/` | **Git Worktree** — একটি আলাদা branch-এ কাজের sandbox। |
| `node_modules/`, `package.json` | Kilo-র নিজস্ব Node.js dependencies। |
| `validate.py`, `yaml_test.py` | Kilo-র validation helper স্ক্রিপ্ট। |

---

## 🔧 MCP Servers (`agent/config.json`)

Kilo এই tools গুলো ব্যবহার করতে পারে:

| MCP Server | ধরন | কাজ |
|---|---|---|
| `github` | Official | GitHub অপারেশন (PR, issues, repo) |
| `git` | Official | Git commands |
| `filesystem` | Official | ফাইল সিস্টেম অ্যাক্সেস |
| `brave-search` | Official | ওয়েব সার্চ |
| `fetch` | Official | URL fetch / HTTP requests |
| `memory` | Official | Persistent memory store |
| `sequential-thinking` | Official | Step-by-step reasoning |
| `postgres` | Official | PostgreSQL ডাটাবেস |
| `sqlite` | Official | SQLite ডাটাবেস |
| `playwright` | Official | ব্রাউজার অটোমেশন |
| `workspace` | **Custom Python** | Dynamic workspace isolation |
| `supabase` | **Custom Python** | Supabase DB operations |
| `cloud-deploy` | **Custom Python** | Render/Railway cloud deploy |
| `github-cicd` | **Custom Python** | GitHub CI/CD integration |
| `ide-trio` | **Custom Python** | IDE trio integration |

---

## 🌿 Worktree: `dirt-octopus`

`worktrees/dirt-octopus/` এ **পুরো SupremeAI প্রজেক্টের একটি Git Worktree কপি** আছে।

- **তৈরি হয়েছে:** `2026-08-08` (`main` branch থেকে)
- **Branch নাম:** `dirt-octopus`
- **উদ্দেশ্য:** Kilo এই branch-এ কাজ করেছে যাতে `main` ব্রেক না হয়
- **Remote:** `origin`
- **Project ID:** `prj-66f96a60c9a2`

> ⚠️ এই worktree-তে একটি **VS Code extension** (`tools/vscode-extension/`) আছে যেটা Kilo-র IDE integration-এর অংশ।

---

## 📋 Plans (১০টি) — Kilo কী কী কাজ করেছে

| # | Plan File | বিষয় | স্ট্যাটাস |
|---|---|---|---|
| 1 | `render-deploy-ci-fix` | Render deploy CI ফিক্স | ✅ |
| 2 | `fix-dataconnect-generated-enoent` | Firebase DataConnect ENOENT error fix | ✅ |
| 3 | `admin-cors-preflight-plan` | Admin CORS preflight fix | ✅ |
| 4 | `admin-503-cors-plan` | Admin 503 + CORS plan | ✅ |
| 5 | `env-secret-drift-detection` | Env/Secret drift detection | ✅ |
| 6 | `lint-warnings-test-timeout-plan` | Lint warnings + test timeout fix | ✅ |
| 7 | `login-blur-fix-plan` | Login blur UI fix | ✅ |
| 8 | **`backend-arch-refactor` ⭐** | **Backend architecture refactoring** (সবচেয়ে বড়) | 🔄 In Progress |
| 9 | `test-coverage-improvement-plan` | Test coverage বাড়ানো | ✅ |
| 10 | `flutter-home-enrich-plan` | Flutter home screen enrichment | ✅ |

---

## 🏗️ Backend Architecture Refactor Plan (সংক্ষেপ)

সবচেয়ে গুরুত্বপূর্ণ plan — `backend/core/` থেকে modules ভাগ করে proper packages-এ নিয়ে যাওয়া:

| Phase | কাজ |
|---|---|
| **P0** | Dead code delete, root clutter সরানো, modular workflow commit |
| **P1-B** | `billing`, `email`, `storage` → `backend/services/*` |
| **P1-C** | `error_*` cluster → `backend/core/errors/` |
| **P1-D** | DB cluster → `backend/database/` |
| **P2-A** | Logging/metrics → `backend/monitoring/` |
| **P2-B** | Middleware → `backend/middleware/` |
| **P3** | `llm_router` → `backend/services/llm/` |
| **P4** | `config.py` split (Out of scope — আলাদা plan) |

**Strategy:** Shim + Gradual migration (old import path কাজ করতে থাকবে, DeprecationWarning সহ)

---

## 📌 সারসংক্ষেপ

> **`.kilo` = Kilo AI coding agent-এর হেডকোয়ার্টার।**  
> এখানে agent-এর কনফিগ, git worktree sandbox, MCP tool setup, এবং সব implementation plan সংরক্ষিত আছে।  
> প্রজেক্টে এটা actively কাজ করেছে — বিশেষত **`backend-arch-refactor`** plan টি এখনো **🔄 in-progress**।

---

*Last updated: 2026-08-15*