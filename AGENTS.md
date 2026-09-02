# Module rules

- A module owns one job, its state, and its files. Never import or write a sibling's files.
- Read siblings only through `ctx.get_prototype(slug)` after `ctx.is_prototype_enabled(slug)`; call documented public functions and verify their contract name and integer version.
- Missing, disabled, malformed, stale, or failing inputs become an explicit `unavailable` state. Hardware and safety checks fail closed. Never add a second robot-control path.
- The simulation owns gameplay truth. Browser Canvas is presentation only; commands are validated server-side. Push changing state with the existing SSE helper.
- Prefer Python stdlib, Flask, plain HTML, CSS, and JavaScript. Add a dependency or abstraction only after a second real use needs it.
- Validate untrusted input, use atomic replacement for persistent JSON, surface exceptions, and include one runnable smoke test for non-trivial logic.
- `hub_init(ctx)` starts owned resources; `hub_stop()` releases them. Importing a module must not start background work.
