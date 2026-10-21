"""
The hub engine — ONE server hosting THREE sandboxes (gamemaster / green / purple).

Each *sandbox* is a folder under `sandboxes/<name>/prototypes/` holding machines.
A *machine* (historically called a prototype) is any sub-folder containing a
`prototype.py` that defines:

    MANIFEST = { "name", "description", "default_page", "pages": [...], "group": "..." }
    bp       = flask.Blueprint(...)   # its pages + API, all paths relative

On startup the hub builds one Flask app per sandbox, mounts each machine's
blueprint under `/s/<sandbox>/p/<slug>`, and serves that sandbox's dashboard at
`/s/<sandbox>/`. The root `/` is a landing page linking the three sandboxes.

Access control
--------------
Every sandbox is password-protected (see `hub-config.json`, generated on first
run). Logging in sets a signed cookie holding the granted roles:

  * `green` / `purple` unlock ONLY their own sandbox.
  * a sandbox marked `"admin": true` (the gamemaster) unlocks ALL sandboxes.

Machines also reach ACROSS sandboxes server-side (e.g. a player's controller
forwards moves to the gamemaster relay). For that, the hub mints a per-sandbox
*service token* at startup and hands it to machines through `hub_init(ctx)`
(`ctx.service_token`); requests carrying it in the `X-HHH-Auth` header
authenticate as that sandbox's role. The gamemaster sandbox lists which of its
machines players may call in its `shared_api` config (API paths only); the
authenticated roles are exposed to the machine via
`request.environ["hhh.roles"]` so it can enforce e.g. side == your-team.

Export / import
---------------
`GET  /s/<name>/api/export` downloads the sandbox's whole `prototypes/` folder
as a zip (the "working setup", settings included).
`POST /s/<name>/api/import` uploads such a zip: the current `prototypes/` is
kept as `prototypes.prev`, the zip's content replaces it, and the hub restarts
itself so the new machines load.

Shared helpers that machines import by plain name (e.g. `import live`) live in
this package's directory, which the engine puts on sys.path during discovery.
Same-named sibling helpers (e.g. each sandbox's `relay_client.py`) are purged
from sys.modules after each machine loads, so every sandbox gets its OWN copy.
"""

import importlib.util
import io
import json
import os
import re
import secrets
import shutil
import socket
import sys
import threading
import time
import traceback
import zipfile
from urllib.parse import quote

from flask import Flask, has_request_context, jsonify, redirect, request, send_file, send_from_directory
from itsdangerous import BadSignature, URLSafeSerializer
from werkzeug.serving import make_server
from .player_join import PlayerJoinLinks, TEAMS, destination, network_origin
from .player_sessions import PlayerSessions, operation_id

# Directory of this engine package. Holds dashboard.html, login.html,
# landing.html, theme.css, live.py.
HUB_DIR = os.path.dirname(os.path.abspath(__file__))

COOKIE_NAME = "hhh_auth"
AUTH_HEADER = "X-HHH-Auth"

# Sandboxes created in hub-config.json on first run. `admin` roles unlock every
# sandbox; `shared_api` lists machines whose /api/ endpoints OTHER roles may
# call (the cross-sandbox surface — keep it minimal).
DEFAULT_SANDBOXES = {
    "gamemaster": {
        "label": "Gamemaster Referee / Operator",
        "accent": "#b6ff3a",
        "admin": True,
        "shared_api": {
            "dobot-mg400-relay": ["green", "purple"],
            "photon-progress": ["green", "purple"],
            "photon-game": ["green", "purple"],
            "mobile-ltz-api": ["green", "purple"],
            "tag-game": ["green", "purple"],
            "2p-tag-game": ["green", "purple"],
            "pickup-game": ["green", "purple"],
            "auto-pickup-game": ["green", "purple"],
            "playfield-areas": ["green", "purple"],
            "webcam": ["green", "purple"],
        },
    },
    "green": {"label": "Green Team", "accent": "#36e07c"},
    "purple": {"label": "Purple Team", "accent": "#b86bff"},
}


def _local_network_ip():
    """Best-effort LAN address for the startup banner and non-request fallback."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            if ip and not ip.startswith("127."):
                return ip
    except OSError:
        pass
    try:
        ip = socket.gethostbyname(socket.gethostname())
        if ip and not ip.startswith("127."):
            return ip
    except OSError:
        pass
    return "localhost"


def load_config(path):
    """Read hub-config.json, filling in any missing pieces (and creating the
    file on first run). Passwords are per-sandbox and operator-editable; the
    secret signs the auth cookies."""
    try:
        with open(path) as f:
            cfg = json.load(f)
        original = json.dumps(cfg, sort_keys=True)
    except (OSError, ValueError, TypeError):
        cfg, original = {}, None
    if not isinstance(cfg, dict):
        cfg, original = {}, None

    if not isinstance(cfg.get("port"), int):
        cfg["port"] = 8000
    if not isinstance(cfg.get("secret"), str) or len(cfg["secret"]) < 32:
        cfg["secret"] = secrets.token_hex(32)
    sandboxes = cfg.get("sandboxes")
    if not isinstance(sandboxes, dict):
        sandboxes = cfg["sandboxes"] = {}
    for name, defaults in DEFAULT_SANDBOXES.items():
        sb = sandboxes.setdefault(name, {})
        for key, value in defaults.items():
            # shared_api is merged per-machine (not all-or-nothing): a config that
            # already has a shared_api still picks up newly shared machines added to
            # the default here, on the next start. Existing entries / operator
            # additions are left untouched.
            if key == "shared_api" and isinstance(value, dict):
                shared = sb.setdefault("shared_api", {})
                if isinstance(shared, dict):
                    for machine, roles in value.items():
                        shared.setdefault(machine, list(roles))
            else:
                sb.setdefault(key, value)
        if not isinstance(sb.get("password"), str) or not sb["password"]:
            sb["password"] = secrets.token_hex(4)

    if json.dumps(cfg, sort_keys=True) != original:
        try:
            with open(path, "w") as f:
                json.dump(cfg, f, indent=2)
                f.write("\n")
        except OSError:
            print(f"WARN: could not write {path}; using in-memory config")
    return cfg


class HubContext:
    """Handed to a machine's optional hub_init(ctx) hook. Lets a machine see
    whether it (or a sibling machine in the SAME sandbox) is enabled, reach a
    sibling's module for its programmatic API, and authenticate cross-sandbox
    HTTP calls (the service token). Looks are live."""

    def __init__(self, sandbox, slug):
        self._sandbox = sandbox
        self.slug = slug

    # -- identity / auth -------------------------------------------------------
    @property
    def sandbox(self):
        """The name of the sandbox this machine lives in (e.g. "green")."""
        return self._sandbox.name

    @property
    def service_token(self):
        """Send as the X-HHH-Auth header to authenticate server-side HTTP calls
        to another sandbox's shared API as THIS sandbox's role."""
        hub = self._sandbox.hub
        sid = request.environ.get('hhh.player_session') if has_request_context() else None
        if sid and self.sandbox in TEAMS:
            return hub._delegate_signer.dumps({'team': self.sandbox, 'sid': sid})
        return hub.service_tokens[self.sandbox]

    @property
    def player_sessions(self):
        """Hub-owned browser identities, admission and revocation."""
        return self._sandbox.hub.player_sessions

    def invalidate_player_links(self):
        self._sandbox.hub.player_join.invalidate()

    def refresh_player_links(self):
        hub = self._sandbox.hub
        if not all(hub.mobile_player_available(team) for team in TEAMS):
            raise ValueError('Both Mobile LTZ modules must be available before reopening joins.')
        origin = network_origin(request.host_url if has_request_context() else hub.local_base,
                                hub.local_base, hub.config.get('player_join_base_url'))
        hub.player_join.snapshot(origin, regenerate=True)

    def register_player_management(self, owner):
        if self.sandbox != 'gamemaster' or self.slug != 'photon-game':
            raise ValueError('Player management must be owned by Photon Game')
        if owner.get('contract') != 'photon.player-management' or type(owner.get('version')) is not int or owner['version'] != 1:
            raise ValueError('Invalid player management contract')
        self._sandbox.hub.player_management = owner

    @property
    def local_base(self):
        """This hub server's own base URL, matching the browser's host when possible."""
        if has_request_context():
            return request.host_url.rstrip("/")
        return self._sandbox.hub.local_base

    @property
    def internal_base(self):
        """Loopback URL for one prototype to call another on this hub.

        Unlike ``local_base``, this must not inherit the incoming Host header:
        that may be a LAN alias or public tunnel which is unsuitable for a
        server-to-itself relay request.
        """
        return f"http://127.0.0.1:{self._sandbox.hub.port}"

    # -- same-sandbox machine lookups ------------------------------------------
    def is_enabled(self):
        """Is THIS machine currently enabled in its sandbox?"""
        return self.slug not in self._sandbox._disabled

    def get_prototype(self, slug):
        """The imported module of a sibling machine, or None if not installed."""
        return self._sandbox._modules.get(slug)

    def is_prototype_enabled(self, slug):
        """Is a sibling machine both installed and enabled?"""
        return slug in self._sandbox._modules and slug not in self._sandbox._disabled


class Sandbox:
    """One sandbox: a Flask app over `<dir>/prototypes/`, gated by its role."""

    def __init__(self, hub, name):
        self.hub = hub
        self.name = name
        self.cfg = hub.config["sandboxes"][name]
        self.dir = os.path.join(hub.sandboxes_dir, name)
        self.machines_dir = os.path.join(self.dir, "prototypes")
        self.settings_path = os.path.join(self.machines_dir, "hub-settings.json")

        self.app = Flask(f"hub_{name}")
        self.app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024
        self._prototypes = []   # discovered + mounted, in display order
        self._modules = {}      # slug -> imported machine module
        self._disabled = set()  # persisted *disabled* slugs (default = enabled)
        self._settings_lock = threading.Lock()

        self._add_routes()

    # ---- settings persistence ----------------------------------------------
    def _load_settings(self):
        try:
            with open(self.settings_path) as f:
                return set(json.load(f).get("disabled", []))
        except (OSError, ValueError, TypeError):
            return set()

    def _save_settings(self):
        try:
            with open(self.settings_path, "w") as f:
                json.dump({"disabled": sorted(self._disabled)}, f, indent=2)
        except OSError:
            pass

    # ---- discovery ----------------------------------------------------------
    def _load_one(self, slug):
        """Import <machines_dir>/<slug>/prototype.py and register its blueprint."""
        path = os.path.join(self.machines_dir, slug, "prototype.py")
        machine_dir = os.path.dirname(path)
        # Sandbox in the module name: green and purple both have e.g.
        # joint-angles-test, and the copies must not collide.
        modname = f"proto_{self.name}_{slug}".replace("-", "_")
        spec = importlib.util.spec_from_file_location(modname, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[modname] = module
        # The machine's own folder goes on sys.path while it imports, so it can
        # `import` sibling helpers (e.g. relay_client.py) by plain name.
        sys.path.insert(0, machine_dir)
        before = set(sys.modules)
        try:
            spec.loader.exec_module(module)
        finally:
            sys.path.remove(machine_dir)
            # Purge sibling helpers from the import cache: another sandbox has
            # its own same-named copies and must load THOSE, not these. The
            # machine keeps its direct references, so this is safe.
            for name in set(sys.modules) - before:
                if name == modname:
                    continue
                mod_file = getattr(sys.modules[name], "__file__", "") or ""
                if mod_file.startswith(self.hub.sandboxes_dir + os.sep):
                    del sys.modules[name]

        manifest = getattr(module, "MANIFEST", {})
        bp = getattr(module, "bp", None)
        if bp is None:
            raise AttributeError("prototype.py defines no `bp` blueprint")

        prefix = f"/p/{slug}"
        # name= overrides the blueprint's own name so two machines can't collide.
        self.app.register_blueprint(bp, url_prefix=prefix, name=modname)
        self._modules[slug] = module

        default_page = manifest.get("default_page", "")
        return {
            "slug": slug,
            "name": manifest.get("name", slug),
            "description": manifest.get("description", ""),
            "group": str(manifest.get("group") or ""),
            "base": prefix,
            "default_url": f"{prefix}/{default_page}".rstrip("/") + ("/" if not default_page else ""),
            "pages": [
                {
                    "label": p.get("label", p.get("path", "Open")),
                    "url": f"{prefix}/{p.get('path', '')}",
                    "newtab": bool(p.get("newtab", False)),
                }
                for p in manifest.get("pages", [{"path": "", "label": "Open"}])
            ],
        }

    def discover(self):
        """Find and mount every machine; report any that fail to load."""
        self._prototypes.clear()
        self._modules.clear()
        if not os.path.isdir(self.machines_dir):
            os.makedirs(self.machines_dir, exist_ok=True)
        # Disabled state must be known before any lifecycle hook runs. Modules
        # are still imported so their routes and dashboard metadata exist, but
        # disabled modules are never started.
        self._disabled.clear()
        self._disabled.update(self._load_settings())
        allowed = self.cfg.get("prototypes")
        if allowed is not None and (not isinstance(allowed, list) or
                                    any(not isinstance(slug, str) for slug in allowed)):
            raise ValueError("prototypes must be a list of module slugs")
        for slug in sorted(os.listdir(self.machines_dir)):
            if allowed is not None and slug not in allowed:
                continue
            if not os.path.isfile(os.path.join(self.machines_dir, slug, "prototype.py")):
                continue
            try:
                self._prototypes.append(self._load_one(slug))
                print(f"  mounted /s/{self.name}/p/{slug}")
            except Exception:
                print(f"  FAILED to load machine '{self.name}/{slug}':")
                traceback.print_exc()
        # Every module is now available for contract-only sibling lookups.
        for slug, module in self._modules.items():
            if slug in self._disabled:
                continue
            hook = getattr(module, "hub_init", None)
            if callable(hook):
                try:
                    hook(HubContext(self, slug))
                except Exception:
                    print(f"  hub_init failed for '{self.name}/{slug}':")
                    traceback.print_exc()

    # ---- auth ----------------------------------------------------------------
    def _gate(self):
        """before_request: allow this sandbox's role, admin roles, and (for the
        machines listed in shared_api) the listed roles' /api/ calls."""
        path = request.path
        if path in ("/login", "/login/join"):
            return None
        roles = self.hub.roles_for_request(request)
        request.environ["hhh.roles"] = roles
        sid = request.environ.get('hhh.player_session')
        if sid and request.method not in ('GET', 'HEAD', 'OPTIONS') and not request.environ.get('hhh.delegated'):
            lock = self.hub.player_sessions.request_lock(sid)
            lock.acquire()
            request.environ['hhh.player_request_lock'] = lock
            if not self.hub.player_sessions.active(sid):
                roles = set()
                request.environ['hhh.roles'] = roles
        if path == "/logout":
            return None
        machine_api = re.match(r"^/p/([^/]+)/api(?:/|$)", path)
        allowed = self.name in roles or self.hub.is_admin(roles)
        if not allowed and machine_api:
            shared = self.cfg.get("shared_api") or {}
            allowed = bool(roles & set(shared.get(machine_api.group(1), ())))
        if not allowed:
            if "/api/" in path or path.startswith("/api"):
                return jsonify({"ok": False, "code": "session_ended", "error": "Session ended. Scan a current QR code or sign in again."}), 401
            nxt = quote(request.script_root + path)
            return redirect(f"{request.script_root}/login?next={nxt}")

        machine = re.match(r"^/p/([^/]+)(?:/|$)", path)
        if machine and machine.group(1) in self._disabled:
            payload = {"ok": False, "error": "machine disabled", "slug": machine.group(1)}
            if machine_api:
                return jsonify(payload), 503
            return payload["error"], 503
        return None

    def _safe_next(self):
        """The ?next= target if it stays on this site, else this sandbox's home."""
        nxt = request.values.get("next", "")
        if nxt.startswith("/") and not nxt.startswith("//"):
            return nxt
        return request.script_root + "/"

    # ---- routes -------------------------------------------------------------
    def _add_routes(self):
        app = self.app
        hub = self.hub

        app.before_request(self._gate)

        @app.teardown_request
        def _release_player_request(error):
            lock = request.environ.pop('hhh.player_request_lock', None)
            if lock is not None: lock.release()

        @app.after_request
        def _no_html_cache(resp):
            """Never cache machine pages (their app code is inline), so editing a
            controller/screen and reloading always picks up the new version."""
            if resp.mimetype == "text/html":
                resp.headers["Cache-Control"] = "no-store, max-age=0"
            if request.path.startswith(('/login', '/api/player-session')) or request.path == '/api/player-join':
                resp.headers['Cache-Control'] = 'no-store'
                resp.headers['Referrer-Policy'] = 'no-referrer'
            sid = request.environ.get('hhh.player_session')
            if sid and resp.status_code == 200:
                if resp.is_streamed and resp.mimetype in ('text/event-stream', 'multipart/x-mixed-replace'):
                    original = iter(resp.response)
                    delegated = bool(request.environ.get('hhh.delegated'))
                    def guarded():
                        try:
                            while self.hub.player_sessions.active(sid):
                                try: chunk = next(original)
                                except StopIteration: break
                                if not self.hub.player_sessions.active(sid): break
                                if not delegated: self.hub.player_sessions.touch(sid)
                                yield chunk
                        finally:
                            if hasattr(original, 'close'): original.close()
                    resp.response = guarded()
                elif resp.mimetype == 'text/html' and not request.environ.get('hhh.delegated'):
                    resp.direct_passthrough = False
                    text = resp.get_data(as_text=True)
                    team = self.hub.player_sessions.rows[sid]['team']
                    resp.set_data(text.replace('</body>', f'<script src="/player-session.js" data-team="{team}"></script></body>'))
            return resp

        @app.route("/")
        def dashboard():
            return send_from_directory(HUB_DIR, "dashboard.html")

        @app.route("/login", methods=["GET", "POST"])
        def login():
            error = ""
            if request.method == "POST":
                password = request.form.get("password", "")
                role = self.hub.role_for_password(self.name, password)
                if role:
                    roles = hub.roles_for_request(request) | {role}
                    resp = redirect(self._safe_next())
                    try:
                        hub.set_auth_cookie(resp, roles, new_session=role in TEAMS)
                        return resp
                    except ValueError as exc:
                        error = str(exc)
                else:
                    time.sleep(0.4)
                    error = "Wrong password."
            elif request.args.get('ended'):
                error = 'Disconnected by the Game Master. Scan the new QR code or sign in again.'
            page = hub.asset("login.html")
            page = (page.replace("__LABEL__", self.cfg.get("label", self.name))
                        .replace("__ACCENT__", self.cfg.get("accent", "#b6ff3a"))
                        .replace("__ERROR__", error))
            return page

        @app.route("/login/join", methods=["POST"])
        def player_join_login():
            # Only this dedicated, public endpoint may redeem an invitation.
            # JSON plus same-origin validation prevents a cross-site form from
            # silently replacing a player's team session.
            if not hub.same_origin_json(request):
                return jsonify(ok=False, error="Join requests must come from this login page."), 403
            if request.content_length is None or request.content_length > 1024:
                return jsonify(ok=False, error="Invalid join request."), 400
            data = request.get_json(silent=True)
            token = data.get('token') if isinstance(data, dict) else None
            # Validation and minting share the admission lock: a request that
            # began before reset cannot redeem an obsolete link after it ends.
            with hub.player_sessions.lock:
                if hub.player_sessions.blocked:
                    return jsonify(ok=False, error='Clean reset in progress. Wait for the new QR codes.'), 503
                if not hub.player_join.accepts(self.name, token):
                    return jsonify(ok=False, error="This join link has expired or was replaced. Scan the current QR code or enter your team password."), 401
                if not hub.mobile_player_available(self.name):
                    return jsonify(ok=False, error="Mobile LTZ is unavailable. Ask the game master to enable it."), 503
                response = jsonify(ok=True, next=destination(self.name))
                hub.set_auth_cookie(response, {self.name}, new_session=True)
            response.headers['Cache-Control'] = 'no-store'
            return response

        @app.route("/api/player-join", methods=["GET", "POST"])
        def player_join_links():
            if not hub.is_admin(request.environ.get('hhh.roles') or set()):
                return jsonify(ok=False, error="Game master access required."), 403
            if request.method == 'POST' and not hub.same_origin_json(request):
                return jsonify(ok=False, error="Regenerate codes from the game master page."), 403
            response = None
            try:
                with hub.player_sessions.lock:
                    if hub.player_sessions.blocked:
                        raise ValueError('Clean reset pending. Finish or retry it before sharing new codes.')
                    for team in TEAMS:
                        if not hub.mobile_player_available(team):
                            raise ValueError(f'{team.title()} Mobile LTZ is unavailable. Enable it before sharing join codes.')
                    origin = network_origin(request.host_url, hub.local_base,
                                            hub.config.get('player_join_base_url'))
                    response = jsonify(hub.player_join.snapshot(origin, regenerate=request.method == 'POST'))
            except Exception as exc:
                app.logger.exception('Player join codes unavailable')
                response = jsonify(status='unavailable', error=str(exc))
                response.status_code = 503
            response.headers['Cache-Control'] = 'no-store'
            return response

        @app.route('/api/player-session/events')
        def player_session_events():
            sid = request.environ.get('hhh.player_session')
            if not sid: return jsonify(error='Player session required'), 401
            return hub.player_sessions.live.stream(lambda: {'active': hub.player_sessions.active(sid)}, interval=2)

        @app.route('/api/player-sessions')
        @app.route('/api/player-sessions/events')
        def player_sessions():
            if not hub.is_admin(request.environ.get('hhh.roles') or set()):
                return jsonify(error='Game master access required'), 403
            def snapshot():
                owner = hub.player_management
                if owner is None or 'photon-game' in hub.sandboxes['gamemaster']._disabled:
                    return {**hub.player_sessions.snapshot(), 'unavailable': True, 'error': 'Photon Game player management unavailable.'}
                return owner['snapshot']()
            if request.path.endswith('/events'):
                return hub.player_sessions.live.stream(snapshot, interval=2)
            return jsonify(snapshot())

        @app.route('/api/player-sessions/clean-reset', methods=['POST'])
        def manage_player_sessions():
            if not hub.is_admin(request.environ.get('hhh.roles') or set()) or not hub.same_origin_json(request):
                return jsonify(error='Use the Game Master player panel.'), 403
            if not request.content_length or request.content_length > 2048:
                return jsonify(error='Invalid management request'), 400
            data = request.get_json(silent=True)
            if not isinstance(data, dict): return jsonify(error='Invalid management request'), 400
            try:
                operation_id(data.get('operation_id'))
                if hub.player_management is None or 'photon-game' in hub.sandboxes['gamemaster']._disabled:
                    raise ValueError('Photon Game player management unavailable.')
                return jsonify(hub.player_management['clean_reset'](data))
            except Exception as exc:
                app.logger.exception('Player management failed')
                return jsonify(ok=False, error=str(exc)), 409

        @app.route("/logout")
        def logout():
            """Drop every role this browser holds that unlocks THIS sandbox."""
            roles = hub.roles_for_request(request)
            sid = request.environ.get('hhh.player_session')
            if sid: hub.player_sessions.revoke(sid)
            keep = {r for r in roles if r != self.name and not hub.is_admin({r})}
            resp = redirect(f"{request.script_root}/login")
            hub.set_auth_cookie(resp, keep)
            return resp

        @app.route("/api/meta")
        def meta():
            roles = request.environ.get("hhh.roles") or set()
            return jsonify({
                "sandbox": self.name,
                "label": self.cfg.get("label", self.name),
                "accent": self.cfg.get("accent", "#b6ff3a"),
                "admin": hub.is_admin(roles),
                "sandboxes": [
                    {"name": n, "label": c.get("label", n), "accent": c.get("accent")}
                    for n, c in hub.config["sandboxes"].items()
                ] if hub.is_admin(roles) else [],
            })

        @app.route("/api/prototypes")
        def prototypes():
            root = request.script_root
            out = []
            for p in self._prototypes:
                out.append({
                    **p,
                    "base": root + p["base"],
                    "default_url": root + p["default_url"],
                    "pages": [{**pg, "url": root + pg["url"]} for pg in p["pages"]],
                    "enabled": p["slug"] not in self._disabled,
                })
            return jsonify(out)

        @app.route("/api/prototypes/<slug>/enabled", methods=["POST"])
        def set_enabled(slug):
            """Persist the choice, stop cleanly when possible, then restart."""
            if slug not in {p["slug"] for p in self._prototypes}:
                return jsonify({"ok": False, "error": "unknown machine"}), 404
            enabled = bool((request.get_json(silent=True) or {}).get("enabled", True))
            with self._settings_lock:
                changed = (slug in self._disabled) == enabled
                self._disabled.discard(slug) if enabled else self._disabled.add(slug)
                self._save_settings()
            if changed and not enabled:
                hook = getattr(self._modules.get(slug), "hub_stop", None)
                if callable(hook):
                    try:
                        hook()
                    except Exception:
                        print(f"  hub_stop failed for '{self.name}/{slug}':")
                        traceback.print_exc()
            restarting = bool(changed and hub._server is not None)
            if restarting:
                hub.schedule_restart(reason=f"{self.name}/{slug} {'enabled' if enabled else 'disabled'}")
            return jsonify({
                "ok": True, "slug": slug, "enabled": enabled,
                "restarting": restarting,
            })

        @app.route("/api/export")
        def export_zip():
            """The whole working setup (machines + their settings) as a zip."""
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr("setup.json", json.dumps({
                    "format": 1,
                    "sandbox": self.name,
                    "exported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                }, indent=2))
                for root, dirs, files in os.walk(self.machines_dir):
                    dirs[:] = [d for d in dirs if d != "__pycache__"]
                    for fname in files:
                        if fname.endswith(".pyc") or fname == ".DS_Store":
                            continue
                        full = os.path.join(root, fname)
                        arc = "prototypes/" + os.path.relpath(full, self.machines_dir)
                        z.write(full, arc)
            buf.seek(0)
            # Optional ?name= from the dashboard's filename prompt; keep it to a
            # safe basename and add the extension ourselves.
            name = re.sub(r"[^A-Za-z0-9._ -]+", "_",
                          (request.args.get("name") or "").strip())
            name = name.rstrip(". ") or f"hhh-{self.name}-setup"
            if name.lower().endswith(".zip"):
                name = name[:-4]
            return send_file(buf, as_attachment=True, mimetype="application/zip",
                             download_name=f"{name}.zip")

        @app.route("/api/import", methods=["POST"])
        def import_zip():
            """Replace this sandbox's prototypes/ with an uploaded setup zip
            (made by /api/export, or any zip of machine folders), keep the old
            folder as prototypes.prev, then restart the hub to load it."""
            upload = request.files.get("zip") or next(iter(request.files.values()), None)
            if upload is None:
                return jsonify({"ok": False, "error": "no zip uploaded"}), 400
            try:
                z = zipfile.ZipFile(io.BytesIO(upload.read()))
            except (zipfile.BadZipFile, OSError):
                return jsonify({"ok": False, "error": "not a zip file"}), 400

            names = [i.filename for i in z.infolist() if not i.is_dir()]
            for n in names:
                parts = n.split("/")
                if n.startswith("/") or ".." in parts or parts[0] == "":
                    return jsonify({"ok": False, "error": f"unsafe path in zip: {n}"}), 400
            # Accept both layouts: a prototypes/ folder (our export) or machine
            # folders at the zip root.
            if any(n.startswith("prototypes/") for n in names):
                root = "prototypes/"
            elif any(re.fullmatch(r"[^/]+/prototype\.py", n) for n in names):
                root = ""
            else:
                return jsonify({"ok": False,
                                "error": "zip holds no prototypes/ folder and no machine folders"}), 400
            wanted = [n for n in names if n.startswith(root) and len(n) > len(root)]
            if not any(re.fullmatch(r"[^/]+/prototype\.py", n[len(root):]) for n in wanted):
                return jsonify({"ok": False, "error": "no <machine>/prototype.py in zip"}), 400

            staging = os.path.join(self.dir, ".import-new")
            shutil.rmtree(staging, ignore_errors=True)
            os.makedirs(staging)
            for n in wanted:
                rel = n[len(root):]
                if "__pycache__" in rel or rel.endswith(".pyc"):
                    continue
                dest = os.path.join(staging, rel)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with z.open(n) as src, open(dest, "wb") as dst:
                    shutil.copyfileobj(src, dst)

            prev = os.path.join(self.dir, "prototypes.prev")
            shutil.rmtree(prev, ignore_errors=True)
            if os.path.isdir(self.machines_dir):
                os.rename(self.machines_dir, prev)
            os.rename(staging, self.machines_dir)

            machines = sorted({n[len(root):].split("/")[0] for n in wanted})
            hub.schedule_restart()
            return jsonify({"ok": True, "restarting": True, "machines": machines})


class _Dispatcher:
    """Tiny WSGI router: /s/<name>/* goes to that sandbox's app (with
    SCRIPT_NAME shifted so the app sees sandbox-relative paths), everything
    else to the root app. `/s/<name>` without the slash redirects to it, so the
    dashboard's relative URLs resolve."""

    def __init__(self, root_app, mounts):
        self.root_app = root_app
        self.mounts = mounts   # {"/s/green": wsgi_app, ...}

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "")
        for prefix, app in self.mounts.items():
            if path == prefix:
                start_response("308 Permanent Redirect",
                               [("Location", prefix + "/"), ("Content-Length", "0")])
                return [b""]
            if path.startswith(prefix + "/"):
                environ["SCRIPT_NAME"] = environ.get("SCRIPT_NAME", "") + prefix
                environ["PATH_INFO"] = path[len(prefix):]
                return app(environ, start_response)
        return self.root_app(environ, start_response)


class Hub:
    """The whole server: three sandboxes + landing page + auth, on one port.

    root_dir    : repo root, holding sandboxes/<name>/prototypes and hub-config.json.
    config_path : where passwords/secret/port live (default <root>/hub-config.json).
    """

    def __init__(self, root_dir, config_path=None):
        self.root_dir = os.path.abspath(root_dir)
        self.sandboxes_dir = os.path.join(self.root_dir, "sandboxes")
        self.config_path = config_path or os.path.join(self.root_dir, "hub-config.json")
        self.config = load_config(self.config_path)
        self.port = self.config.get("port", 8000)
        self.lan_ip = _local_network_ip()
        self.local_base = f"http://{self.lan_ip}:{self.port}"
        self._server = None

        self._signer = URLSafeSerializer(self.config["secret"], salt="hhh-auth")
        self._delegate_signer = URLSafeSerializer(self.config['secret'], salt='hhh-player-delegation')
        self.player_join = PlayerJoinLinks()
        self.player_sessions = PlayerSessions(os.path.join(self.root_dir, '.mobile-ltz-runtime', 'player-access.json'))
        self.player_management = None
        # Per-sandbox service tokens for cross-sandbox machine calls. Minted
        # fresh per process: machines receive them via hub_init on every start.
        self.service_tokens = {name: secrets.token_hex(16)
                               for name in self.config["sandboxes"]}
        self._token_roles = {tok: name for name, tok in self.service_tokens.items()}

        self.sandboxes = {name: Sandbox(self, name) for name in self.config["sandboxes"]}
        self.root_app = self._build_root_app()
        self.wsgi = _Dispatcher(
            self.root_app,
            {f"/s/{name}": sb.app for name, sb in self.sandboxes.items()},
        )

    # ---- auth helpers --------------------------------------------------------
    @staticmethod
    def same_origin_json(req):
        origin = req.headers.get('Origin')
        return req.is_json and (origin is None or origin == req.host_url.rstrip('/'))

    def mobile_player_available(self, team):
        sandbox = self.sandboxes.get(team)
        return bool(team in TEAMS and sandbox and not sandbox.cfg.get('admin')
                    and 'mobile-ltz' in sandbox._modules
                    and 'mobile-ltz' not in sandbox._disabled)

    def roles_for_request(self, req):
        """Every role this request proves: service token first, then cookie."""
        roles = set()
        token = req.headers.get(AUTH_HEADER, "")
        if not token:
            auth = req.headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                token = auth[7:]
        role = self._token_roles.get(token)
        if role:
            roles.add(role)
        elif token:
            try:
                delegated = self._delegate_signer.loads(token)
                side, sid = delegated.get('team'), delegated.get('sid')
                if side in TEAMS and self.player_sessions.active(sid, side):
                    roles.add(side)
                    req.environ['hhh.player_session'] = sid
                    req.environ['hhh.delegated'] = True
            except (BadSignature, AttributeError, TypeError):
                pass
        raw = req.cookies.get(COOKIE_NAME)
        if raw:
            try:
                data = self._signer.loads(raw)
                for role in data.get('roles', []):
                    if role not in self.config['sandboxes']: continue
                    if role not in TEAMS or self.config['sandboxes'][role].get('admin'):
                        roles.add(role)
                    elif self.player_sessions.active(data.get('sid'), role):
                        roles.add(role)
                        req.environ['hhh.player_session'] = data['sid']
                        self.player_sessions.touch(data['sid'], req.remote_addr)
            except (BadSignature, AttributeError, TypeError):
                pass
        return roles

    def is_admin(self, roles):
        return any(self.config["sandboxes"].get(r, {}).get("admin") for r in roles)

    def role_for_password(self, sandbox_name, password):
        """The role a password typed at `sandbox_name`'s login earns: that
        sandbox's own role, or an admin role typed anywhere."""
        if not password:
            return None
        candidates = [sandbox_name] + [n for n, c in self.config["sandboxes"].items()
                                       if c.get("admin")]
        for name in candidates:
            expected = self.config["sandboxes"].get(name, {}).get("password", "")
            if expected and secrets.compare_digest(password, expected):
                return name
        return None

    def set_auth_cookie(self, resp, roles, new_session=False):
        if roles:
            data = {'roles': sorted(roles)}
            teams = set(roles) & set(TEAMS)
            if teams and not self.is_admin(roles):
                team = sorted(teams)[0]
                sid = request.environ.get('hhh.player_session')
                if new_session or not self.player_sessions.active(sid, team):
                    sid = self.player_sessions.create(team, request.remote_addr)
                data = {'roles': [team], 'sid': sid}
            resp.set_cookie(COOKIE_NAME, self._signer.dumps(data),
                            path="/", httponly=True, samesite="Lax",
                            max_age=14 * 24 * 3600)
        else:
            resp.delete_cookie(COOKIE_NAME, path="/")

    # ---- assets / root app ----------------------------------------------------
    def asset(self, name):
        with open(os.path.join(HUB_DIR, name), encoding="utf-8") as f:
            return f.read()

    def _build_root_app(self):
        app = Flask("hub_root")

        @app.route("/")
        def landing():
            cards = [{"name": n, "label": c.get("label", n),
                      "accent": c.get("accent", "#b6ff3a")}
                     for n, c in self.config["sandboxes"].items()]
            return self.asset("landing.html").replace("__SANDBOXES__", json.dumps(cards))

        @app.route("/theme.css")
        def theme_css():
            """Shared visual theme, linked by every machine page (public)."""
            return send_from_directory(HUB_DIR, "theme.css")

        @app.route('/player-session.js')
        def player_session_script():
            return send_from_directory(HUB_DIR, 'player-session.js', max_age=0)

        @app.route("/Video1.mp4")
        def mission_video():
            """Public mission briefing video for the Tag Game player screen."""
            return send_from_directory(self.root_dir, "Video1.mp4")

        return app

    # ---- restart (after an import) --------------------------------------------
    def schedule_restart(self, delay=0.8, reason="configuration changed"):
        """Re-exec this process shortly, after the import response flushes."""
        def _go():
            print(f"\nRestarting hub ({reason})...", flush=True)
            # The listening socket is inheritable and would survive the exec,
            # leaving the new process unable to bind the port — close it first.
            server = self._server
            if server is not None:
                try:
                    server.socket.close()
                except OSError:
                    pass
            os.execv(sys.executable, [sys.executable] + sys.argv)
        threading.Timer(delay, _go).start()

    # ---- run -------------------------------------------------------------------
    def run(self, host="0.0.0.0", port=None):
        if port is not None:
            self.port = port
            self.local_base = f"http://{self.lan_ip}:{self.port}"
        # Shared engine helpers (e.g. live.py) importable by plain name from
        # machine modules, without the machine knowing where the engine lives.
        if HUB_DIR not in sys.path:
            sys.path.insert(0, HUB_DIR)
        print("Discovering machines:")
        for sb in self.sandboxes.values():
            sb.discover()
        print(f"\nHub local:   http://localhost:{self.port}")
        print(f"Hub network: {self.local_base}")
        for name, cfg in self.config["sandboxes"].items():
            label = cfg.get("label", name)
            print(f"  {label:<14} {self.local_base}/s/{name}/   "
                  f"password: {cfg.get('password')}")
        print(f"(passwords are editable in {os.path.relpath(self.config_path, os.getcwd())})",
              flush=True)
        self._server = make_server(host, self.port, self.wsgi, threaded=True)
        # Private bootstrap for the allowlisted mobile UI relay. Scope it to
        # this port so another development hub cannot redirect its identity.
        green = self.sandboxes.get('green')
        if green and 'mobile-ltz' in green._modules:
            directory = os.path.join(self.root_dir, '.mobile-ltz-runtime')
            os.makedirs(directory, mode=0o700, exist_ok=True)
            token_path = os.path.join(directory, f'client-auth-{self.port}')
            temporary = token_path + '.tmp'
            with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w') as handle:
                handle.write(self.service_tokens['green'])
            os.replace(temporary, token_path)
        self._server.serve_forever()
