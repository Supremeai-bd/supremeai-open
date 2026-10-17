# Bridge Canary Probe — 2026-10-17

Health probe for the bridge intake gate before the Bangla Voice Service WO wave (issue #540, task bridge-20261017-bangla-voice).

- Probe taskId: bridge-20261017-probe-voice
- Trigger: L22 canary protocol (fail-closed intake verification, cumulative WAF score guard)
- Expected: intake accepts, patch branch bridge/bridge-20261017-probe-voice appears with this file byte-exact.
- Cleanup: safe to revert/delete after verification; carries no runtime semantics.
