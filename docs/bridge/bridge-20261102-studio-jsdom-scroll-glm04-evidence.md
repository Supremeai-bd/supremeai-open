# Evidence — #5190 (studio: jsdom scrollIntoView test-env gap)

By **GLM Agent 04 (Job 486718)**, 2026-11-02 ~04:20Z. Claim lease
`work_claim #5190 GRANT_NEW @04:08:32Z`. Evidence + exact patch proposal
only — target is the **satellite repo `supremeai-studio`** (outside this
open-repo agent envelope per loop rules), so NO 'Closes' line; closure
belongs to the Studio maintainer.

## Premise re-verified live (stale-incident guard)

- `github_workflow_runs` supremeai-studio recent-12: latest main run is
  **41309314254 (2026-11-01T13:02, pipeline, conclusion=failure)** — the
  very run the issue cites; **no newer main run exists** → incident still
  current, not superseded. (Earlier mains same day: 2x failure, 3x success
  — the red window started after the component/effect landed.)
- Failed log pull (`get_failed_logs`): only a 2.1KB boot snippet was
  returned — the `scrollIntoView` error line itself is UNSEEN from this
  envelope; the issue's quoted log (`TypeError: ...scrollIntoView is not a
  function` at SplitStudioView.tsx:98) remains the primary log evidence.
- `latestClaim` via feedback plane: None (single-owner claim clean).

## Code read live (both files, via github_read_file)

- `src/test/setup.ts` (2002 B): mocks present = localStorage, EventSource,
  fetch/AbortSignal (with an honesty-note comment). **No scrollIntoView
  mock** — issue confirmed.
- `src/components/studio/SplitStudioView.tsx` (590 lines), call site:
  ```tsx
  97:   useEffect(() => {
  98:     messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  99:   }, [messages, isGenerating]);
  ```
  Browser API called from an effect — correct production behavior; the gap
  is purely the jsdom test DOM (jsdom has no layout engine).

## Exact patch proposal (copy-paste grade, minimal)

Append to `src/test/setup.ts` (matches the file's existing
`Object.defineProperty`/vi.fn idiom):

```ts
// jsdom does not implement Element.scrollIntoView (no layout engine).
// SplitStudioView auto-scrolls on new messages; stub so effects don't throw.
Object.defineProperty(Element.prototype, 'scrollIntoView', {
  value: vi.fn(),
  writable: true,
});
```

Notes: mock on `Element.prototype` (widest correct surface,
assertion-friendly); component contract intact (no guard, no skipped
test); `vi` already imported → diff is +5 lines, no new imports.

## Acceptance mapping & boundaries

- Add minimal mock → **proposed above** (exact, dependency-free).
- Keep behavior/assertions intact → honored (no test skipped, no guard added).
- Re-run suite/lint/typecheck/build + confirm green main → **Studio
  maintainer step** (studio workspace is outside this repo's sandbox;
  honest boundary, not an omission).
- Alert-class note: two consecutive mains red on 11-01 for a missing jsdom
  stub — a one-line setup-checklist entry ("new DOM-API usage in components?
  stub in setup.ts") would prevent the recurrence class; left to the owner.
