# Frontend simplicity contract

The frontend is a viewer and interaction layer, not a second backend.

## Rules for future changes

- The backend remains authoritative for authorization, policy, orchestration, memory, audit, and operational hardening.
- Prefer one readable viewer path: one URL, one API boundary, one auth state, and one navigation registry.
- The normal user navigation should contain only understandable, working viewer destinations.
- Do not add MCP server management, memory management, policy editing, topology controls, or global realtime infrastructure to the viewer flow unless the product request explicitly requires it.
- Keep advanced/admin routes isolated and reachable only when their audience and use case are clear.
- For read-only data screens, implement only loading, connected/loaded, empty, and backend-error states.
- Prefer local component state for page data. Add global state only for genuinely cross-page concerns such as auth or theme.
- Comments should explain architectural boundaries, not repeat JSX or migration history.

## Viewer journey

1. Open the app or a shared URL.
2. Show a clear loading state while the backend is contacted.
3. Render all data returned for the viewer role in a readable, read-only format.
4. Show a useful empty state when the backend returns no data.
5. Show a plain error and retry action when the backend cannot be reached.

If a proposed frontend change makes this journey harder to understand, stop and simplify it before adding more infrastructure.

## Explicit non-goals

Do not introduce a new MCP server, memory server, client-side policy engine, duplicate API client, or global websocket/SSE connection for the simple viewer experience.

## User-first rules for future agents

- Anonymous read-only viewing is the default. Never force login for a normal viewer journey unless the backend explicitly says the shared server is private.
- The owner controls sharing and role choices. Do not silently downgrade an owner-selected role in the frontend; render the backend's allowed role and keep admin-only protection isolated to admin actions.
- A shared MCP URL must be easy to copy and paste. Do not make users configure an account before copying or opening a URL.
- Never make users log in again during ordinary navigation, refresh, reconnect, or data viewing. Preserve the existing session when authentication is genuinely required.
- The viewer must not show a login form, account setup, security prompt, OTP, or permission dialog during the normal URL → Open → Read journey. If the shared server is private, explain that plainly and provide only the minimum access step required by the backend.
- Treat zero-friction viewing as a product requirement: no forced account, no repeated authentication, no token field on the first screen, and no technical setup before the first data request.
- Do not add security prompts, OTP, permission dialogs, device checks, token fields, or confirmations to ordinary read-only actions. Sensitive write/admin actions may use their own isolated flow.
- Keep optional credentials hidden until they are needed. The first screen should ask for one thing: the shared URL.
- Backend security is not a reason to expose policy, memory, MCP management, audit, or infrastructure controls in the viewer UI.
- Every public viewer screen must have plain loading, success, empty, and error states with a retry path. Do not show stack traces or internal implementation terms.
- Prefer the smallest number of clicks: paste URL, press Open, read data. If a change adds a step, explain why it is unavoidable before adding it.
- Use simple English or Bengali labels that describe the user goal. Avoid terms such as cockpit, governance, tower, swarm, neural memory, or policy unless the user explicitly needs them.
- Mobile users are first-class users: controls must fit narrow screens, use full-width primary actions when useful, and avoid dense tables that require awkward horizontal scrolling.
- Comments at architectural boundaries must protect this contract. Do not add long migration commentary inside JSX or create new frontend infrastructure to solve a backend concern.

// Future agents: keep this file short and consult it before adding frontend infrastructure.
// Backend complexity may remain behind the API boundary; it does not belong in the viewer UI.
