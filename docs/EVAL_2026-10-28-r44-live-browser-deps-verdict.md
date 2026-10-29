# R44 Live Browser Deps — Evaluation Verdict (2026-10-28)

Lane: **R44** (first fully-unclaimed number per the #2042 header reconciliation note; the allocation rule's stale "next free: R39" pointer is corrected in the next index drift pass)
Source: **#2042** (ecosystem-scout Job 478520; verdict requested: `evaluate` — split A/B/C)

## Verdict

| Scout option | Ruling | This change |
|---|---|---|
| **A — make the live surface auditable** | **ADOPT — sub-option (b)** | `browser/requirements.txt` (23-pin closure) + Dockerfile installs `-r requirements.txt` |
| **B — dead-text disposition** (6-file mirror family + 6 orphaned Dockerfiles, F-9 intent) | **DEFER — maintainer lane** | Untouched; the guard's fidelity to dead text is unchanged by this PR |
| **C — identity reconciliation** (relay-vs-sandbox wording) | **DEFER — maintainer lane** | Dockerfile comment left verbatim |

## Option A: why (b), and what landed

Sub-option (a) (`pip install .` from pyproject) was rejected for this PR: it makes pyproject the install SSOT, which drags the layer-1 identity question (Option C territory) and a package-layout decision into a dep-security change. Sub-option (b) is the smallest auditable contract: one manifest + two Dockerfile lines, zero guard changes, zero blueprint changes (`browser/render.yaml` `dockerfilePath: ./Dockerfile` untouched — build context resolves `COPY requirements.txt ./` to the new file).

What landed:

1. **`browser/requirements.txt`** — the previously-unpinned inline set (`fastapi`, `uvicorn[standard]`, `httpx`, `pydantic`) resolved to a pinned 23-package closure. Provenance: pip 26.2.2 clean-room `--dry-run --report` with `--python-version 3.11 --only-binary=:all:` (matches the `python:3.11-slim` build image), dated 2026-10-28. Header carries the #1969 doctrine: no auto bumps, maintainer decisions only.
2. **`browser/Dockerfile`** — the dead `COPY pyproject.toml ./` (copied, never installed — layer 1) is replaced by `COPY requirements.txt ./`; the float-at-build-time `RUN pip install fastapi "uvicorn[standard]" httpx pydantic` becomes `RUN pip install --no-cache-dir -r requirements.txt`. Comment line (Option C) untouched.

## Audit receipts (this cycle, dated 2026-10-28)

- **Resolution cross-check**: scout's archived synthesized audit = 23 resolved dependencies; this cycle's clean-room 3.11 resolution = 23 packages. Independent agreement.
- **pip-audit 2.10.1 (PyPA) requirements mode on the landed manifest**: 23 audited, **0 known vulnerabilities**, exit 0. Archived JSON in the landing PR evidence. Per the guard's own doctrine (the #2033-embodied lesson): the landing floor is the LIVE audit result — and it is empty, so **zero baseline changes** are needed (a clean manifest produces no `findings` pairs; `compare()` sees no new pair).
- **`py_dep_cve_guard.py --check` after landing**: `surface: 11 tracked requirements manifest(s)` (was 10 — the guard's tracked discovery now covers the ONE Render-deployed service), `ratchet clean`, exit 0. The 1 vulnerable pair on the tree remains the pre-existing baselined landing floor (pytest@8.4.2, supreme-node — maintainer bump lane, out of scope here).
- **Import coverage check**: `browser/server.py` runtime imports (`httpx`, `fastapi`, `pydantic`) + uvicorn CMD are all inside the pinned closure; `browser/main.py` is stdlib-only.

## Residuals explicitly deferred (not silently dropped)

- Layer-1 divergence: `browser/pyproject.toml` remains declared-but-never-installed text. Its disposition (install SSOT vs archive note) rides the same maintainer lane as Option B.
- Option B: the 6-file requirements mirror family and 6 orphaned Dockerfiles keep their F-9 status notes until a maintainer attaches or archives them; until then every mirror-integrity observation is integrity of dead text (the scout's phrasing stands).
- Option C: the Dockerfile's "lightweight Gemini cookie relay" identity comment is untouched.
- The satellite render blueprint (`infrastructure/mcp-control-plane/render.yaml`) was not audited this cycle — the scout's noted follow-up surface stands.

## Benchmark honesty

One dated resolution + one dated audit run, both reproducible from the archived artifacts; no image build was executed (the gate audits the manifest plane, not the image plane — #1735 boundary respected); no runtime-behavior claims.
