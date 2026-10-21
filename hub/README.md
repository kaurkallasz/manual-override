# hub — the engine

This folder is the **engine**: the content-free part that hosts *machines* in
password-protected *sandboxes*. It knows how to discover, mount, gate, and
serve them, but ships none itself. The machines — the local content you build
and edit — live under `../sandboxes/<name>/prototypes/`.

It started as a vendored copy of Manual Override's single-sandbox engine and
has diverged: one server now hosts several sandboxes with auth, service
tokens, and setup export/import.

## What's here

| File             | Role                                                            |
|------------------|-----------------------------------------------------------------|
| `__init__.py`    | `Hub` (config/auth/dispatch) + `Sandbox` (discovery, mounting, dashboard, export/import) |
| `live.py`        | shared push helper (SSE); machines `import live`                |
| `dashboard.html` | the sandbox shell UI (one tab per machine, export/import header)|
| `login.html`     | per-sandbox password page                                       |
| `landing.html`   | `/` — links the sandboxes                                       |
| `theme.css`      | shared visual theme, linked by every machine page (public)      |

## Running

Use the launcher at the repo root:

```bash
pip install -r requirements.txt
python ../hub.py     # http://localhost:8000
```

Or embed the engine directly:

```python
from hub import Hub
Hub(root_dir="/path/to/repo").run(port=8000)   # expects <root>/sandboxes/<name>/prototypes
```

Sandbox names, labels, accents, passwords, the port, and the cookie secret live
in `<root>/hub-config.json`, created on first run (see `DEFAULT_SANDBOXES` in
`__init__.py`). The startup banner prints every sandbox's URL + password.

## URLs and auth

* `/` — landing page (public); `/theme.css` (public).
* `/s/<sandbox>/` — that sandbox's dashboard; `/s/<sandbox>/p/<slug>/...` — its machines.
* `/s/<sandbox>/login`, `/logout` — cookie auth. A sandbox's password unlocks
  it; a sandbox configured `"admin": true` (the gamemaster) unlocks all.
* `shared_api` in a sandbox's config (e.g. `{"dobot-mg400-relay": ["green", "purple"]}`)
  lets the listed roles call that machine's `/api/` endpoints across the sandbox
  boundary. The hub puts the caller's authenticated roles in
  `request.environ["hhh.roles"]` so the machine can enforce finer rules
  (the relay enforces side == team).
* Server-side cross-sandbox calls authenticate with the per-process **service
  token** a machine receives via `hub_init(ctx)` (`ctx.service_token`), sent as
  the `X-HHH-Auth` header.
* `/s/<sandbox>/api/export` (zip download) and `/api/import` (zip upload —
  replaces `prototypes/`, keeps the old one as `prototypes.prev`, restarts the
  hub).

### Player QR sign-in

Laser Tag Y shows Green/Purple join cards backed by the hub's
`GET /s/gamemaster/api/player-join` endpoint. Only an authenticated admin can
read or regenerate them (`POST` with same-origin JSON). QR images are generated
locally using the game's existing OpenCV dependency. Missing/disabled Mobile LTZ
modules, unavailable QR support, or an unusable network address produce an
explicit unavailable state.

Each link contains a random 192-bit team invitation in `#join=…`, valid for eight
hours and reusable for reconnection. The login page immediately removes the
fragment, posts the token to its own `/login/join`, and receives a normal
HttpOnly session cookie containing exactly that team. The destination is fixed
to `/s/<team>/p/mobile-ltz/`. No password, service token, or admin cookie is
shared. Invalid links leave the ordinary password form usable.

Regenerating replaces both invitation tokens. Expired codes refresh automatically;
a hub restart also invalidates old links and player browser sessions. Regeneration
alone leaves signed-in sessions connected. Player sessions otherwise last up to
14 days and can log out normally.

The admin-only `/api/player-sessions` and `/api/player-sessions/events` routes
expose `hub.player-sessions` v1: one row per browser sign-in, observed IP, selected
team profile name, connection/control status and last seen. IPs are observed at
the Hub, so a hosted relay may appear as the same local address for every phone.
Multiple browsers can use the same profile and IP. This is a presence list, not
an IP ban or a unique physical-person identity.

`POST /s/gamemaster/api/player-sessions/clean-reset` requires admin authentication,
same-origin JSON and a unique `operation_id`. Photon Game registers the
`photon.player-management` v1 owner through `ctx.register_player_management`.
It closes admission, invalidates invitations and every player session (including
offline clients), drains earlier player requests, releases both relay leases and
uses Game's existing Reset path to return the active event to player selection.
Saved profiles/results/upgrades/settings/calibration are preserved; unfinished
attempts receive the ordinary aborted-result settlement. No new event is made.
Fresh QR codes become available only after reset and required physical stops
succeed. Retry uses the same operation ID; a completed duplicate does nothing.

Incomplete reset state is atomically persisted in
`.mobile-ltz-runtime/player-access.json`; a server restart cannot reopen it.
While pending, player sign-in and motion remain blocked, and Game Master sees
the failure and a Retry clean reset action. Operator feedback connection and
safe stop paths remain available for recovery. New events and ordinary QR
regeneration do not automatically disconnect players. There is no individual
player-kick endpoint or button.

Player cookies identify a browser session. `ctx.service_token` inside a player
request delegates that identity to backend relay workers; revoked identities
cannot continue sending commands. Player SSE/video streams check revocation
before each emitted chunk. The outer player page monitors a presence stream
and redirects to sign-in when the session ends, including after returning from
the background. Admin sessions remain connected. Browser identities are kept
only for this Hub process; old team-only cookies must sign in again after upgrade.

Links use the browser's server origin, falling back to the hub's LAN address
when the operator uses localhost. Phones need access to that network. Optional
`player_join_base_url` in `hub-config.json` overrides the origin; it must point
to this hub over HTTP(S), without a path, query, credentials, or fragment. This
is not the separately hosted mobile relay's URL. No public origin is required
for game Wi-Fi use.

Green/Purple dashboards initially show only Mobile LTZ, even with an old saved
tab or hash. **Show other tabs** reveals the other enabled modules for that visit;
admin users retain the full dashboard. This is a navigation filter, not module
disabling or a change to API permissions, so Mobile LTZ dependencies keep working.

Verification: `.venv/bin/python -m unittest discover -s tests -p test_player_join.py`
and `node --test tests/hub_navigation.test.js`. For browser checks, run
`tests/player_join_fixture.py`, then `node tests/player_join_browser.cjs` with
Playwright available. The fixture uses the real hub and pages, temporary auth,
and no game or robot owners.

## The machine contract

A machine is any sub-folder of a sandbox's `prototypes/` with a `prototype.py`
that defines:

```python
MANIFEST = {
    "name": "My module", "description": "One job.",
    "default_page": "", "pages": [...],
    "group": "Photon Engine",  # optional dashboard grouping only
}
bp       = flask.Blueprint(...)   # pages + API, all paths relative to /s/<sandbox>/p/<slug>/
```

Optional: a `hub_init(ctx)` hook receives a `HubContext`:

* `ctx.sandbox` — the sandbox name (a player machine's team);
* `ctx.service_token` — auth for cross-sandbox HTTP calls;
* `ctx.local_base` — this server's own base URL (`http://127.0.0.1:<port>`);
* `ctx.is_enabled()` / `ctx.get_prototype(slug)` / `ctx.is_prototype_enabled(slug)`
  — same-sandbox machine lookups.

An optional `hub_stop()` hook releases module-owned threads or devices. Disabled
modules are imported but do not receive `hub_init`; all of their page and API
routes return HTTP 503. Changing enabled state restarts the hub so every module
sees a clean dependency graph.

Shared helpers like `live` are importable by plain name — the engine puts this
folder on `sys.path` during discovery. A machine's OWN sibling modules
(e.g. `relay_client.py`) import by plain name too; the engine purges them from
`sys.modules` after each machine loads so the same-named copy in another
sandbox loads independently.

Keep page URLs relative (or derive the sandbox prefix from
`location.pathname`, as tag-game does) — machines are mounted under
`/s/<sandbox>/p/<slug>`, and the prefix is not fixed.
