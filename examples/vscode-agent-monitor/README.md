# SupremeAI VS Code Agent Monitor (issue #333 reference)

Real-time agent execution monitor for the IDE: a status-bar indicator plus a
streaming event output channel, fed by a reconnecting WebSocket client that
speaks the `docs/WEBSOCKET_SPEC.md` frame contract
(`api-schemas/websocket-events.schema.json`).

## Architecture (testability first)

| Module | Role |
| ------ | ---- |
| `src/statusLogic.ts`  | PURE: fail-closed frame validation (spec envelope, poka-yoke payload pinning), seq-gap resync verdicts, idle/busy/error state machine, output-line renderer |
| `src/resilience.ts`   | PURE: exponential reconnect backoff with full jitter + reset; bounded output buffer that drops oldest lines behind an explicit marker (a flooded stream can never freeze the IDE) |
| `src/wsTransport.ts`  | PURE (factory injected): reconnecting WebSocket pump — callbacks only, never sync-throws into the extension host; resync = reconnect with a fresh seq space |
| `src/extension.ts`    | the ONLY vscode import: status bar item (error theme color on failures), output channel, command wiring, honest WebSocket runtime resolution (global WebSocket, else the ws package, else a visible warning) |

## Contracts honored

- AC1 status bar: `idle` / `busy` / `error` (error sticks until the next
  `agent:started`); tooltips carry the last event + seq.
- AC2 output channel: one line per accepted frame (START/THINK/CALL/RESULT/
  DONE/ERROR/heartbeat) through the bounded buffer.
- AC3 resilience: dropped malformed frames are logged, never half-interpreted;
  seq gaps trigger resync per the spec MUST; reconnects are scheduled with
  capped backoff; dispose() cancels everything.
- Honesty: no fabricated status — the widget only ever reflects received,
  validated frames.

## Verification (issue contract)

```bash
npm run compile   # strict tsc (vscode + node typings, noEmitOnError)
npm test          # 11 offline tests against the compiled pure modules
```

The vscode layer is type-checked but never executed in tests — no electron
download needed; the pure modules carry all the runtime logic.
