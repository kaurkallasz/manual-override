"""
Shared live-state helper for prototypes — push, don't poll.

A prototype that has changing state should let its pages SEE changes instead of
polling for them. Wrap one `LiveState` per prototype and expose a Server-Sent
Events route built from it; pages open an `EventSource` on that route and the
server pushes a fresh snapshot whenever the state moves.

Two ways a change reaches clients, combined in one stream:

  * **bump()** — call it right after you mutate state. Connected clients are
    woken immediately, so an event-driven store (areas, a tween) shows up with no
    lag. Give such a stream a long `interval` (the default) — every real change
    already bumps, so the interval is just a keep-alive.

  * **interval** — the stream also re-snapshots every `interval` seconds even
    without a bump, so state that changes with no discrete event (sampled from
    hardware: a robot pose, camera fps, tracked tags) still gets through. Give
    such a stream a short `interval` (e.g. 0.2) and don't bump at all.

Either way, identical consecutive snapshots are coalesced into a ':' keep-alive
instead of being resent — so a quiet store stays quiet and a sampled source only
emits frames that actually differ.

Usage (in a prototype's prototype.py):

    import live
    _live = live.LiveState()

    def _snapshot():
        with _lock:                       # may take your own data lock
            return {"rev": _rev, "items": list(_store.values())}

    # event-driven: bump on every mutation, long keep-alive interval
    def _touch():
        ...
        _live.bump()

    @bp.route("/api/events")
    def events():
        return _live.stream(_snapshot)            # push on bump

    # sampled: no bump, short interval
    @bp.route("/api/events")
    def events():
        return _live.stream(_snapshot, interval=0.2)   # push ~5x/s when changed

On the page, replace `setInterval(poll, …)` with:

    const es = new EventSource(U('/api/events'));   // auto-reconnects
    es.onmessage = e => applyState(JSON.parse(e.data));
"""

import json
import threading
import time

from flask import Response


class LiveState:
    """A version counter + condition that an SSE stream waits on. One per
    prototype; the snapshot callable you hand to stream() decides what's sent."""

    def __init__(self):
        self._cond = threading.Condition()
        self._ver = 0
        self._shared_lock = threading.Lock()
        self._shared = None

    def bump(self):
        """Wake every connected stream — call after mutating state."""
        with self._cond:
            self._ver += 1
            self._cond.notify_all()

    def stream(self, snapshot, interval=15.0, *, shared=False, static_fields=()):
        """Return a Flask SSE `Response` that pushes `snapshot()` on every change.

        `snapshot` is a no-arg callable returning a JSON-serialisable dict. It is
        called OUTSIDE this object's lock, so it may take the prototype's own data
        lock freely (the two locks never nest, so they can't deadlock).

        `interval` is the longest gap between re-checks: short for sampled state
        that changes without a bump, long (keep-alive) for bump-driven state.

        Opt-in `shared` prepares/encodes once per version or timeout for all
        subscribers using the same callable. `static_fields` opts into named
        `update` events omitting those fields while unchanged. First delivery,
        reconnect and changes to static fields always receive a full message.
        Default streams retain their original full-snapshot behavior.
        """
        cond = self._cond
        state = self
        fields = tuple(static_fields)

        def prepare():
            value = snapshot()
            if not fields:
                payload = json.dumps(value, default=str)
                return payload, payload, None
            static = {key: value[key] for key in fields if key in value}
            dynamic = {key: item for key, item in value.items() if key not in fields}
            compact = {"default": str, "separators": (",", ":")}
            return (
                json.dumps(value, **compact),
                json.dumps(dynamic, **compact),
                json.dumps(static, sort_keys=True, **compact),
            )

        def prepared(version):
            if not shared:
                return prepare()
            # Snapshot outside the condition lock: producers can bump while
            # taking their own locks. Retain only one bounded cache entry.
            with state._shared_lock:
                cached = state._shared
                key = (snapshot, fields, version)
                if cached is None or cached[0] != key or time.monotonic() >= cached[1]:
                    payloads = prepare()
                    state._shared = (key, time.monotonic() + interval, payloads)
                return state._shared[2]

        def gen():
            last_ver = -1
            last_sent = None
            last_static = None
            while True:
                with cond:
                    # wake on a bump, or re-check after `interval` seconds. We
                    # only hold the lock to read the version, never to snapshot.
                    cond.wait_for(lambda: state._ver != last_ver, timeout=interval)
                    last_ver = state._ver
                payload, update, static = prepared(last_ver)
                if payload != last_sent:
                    patch = bool(fields) and last_sent is not None and static == last_static
                    last_sent = payload
                    last_static = static
                    yield ("event: update\ndata: " + update if patch else "data: " + payload) + "\n\n"
                else:
                    yield ": ping\n\n"   # unchanged — keep-alive only

        return Response(gen(), mimetype="text/event-stream", headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # don't let a proxy buffer the stream
        })
