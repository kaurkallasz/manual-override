"""Real hub/auth, Laser Tag Y and Mobile LTZ pages; no game or robot modules.

Run with .venv/bin/python tests/player_join_fixture.py, then the browser smoke.
All settings and invitation state are temporary.
"""
from pathlib import Path
import sys
import tempfile
from werkzeug.serving import make_server
from test_player_join import fixture_hub, ROOT
from hub import Hub, HubContext, HUB_DIR


if __name__ == '__main__':
    sys.path.insert(0, HUB_DIR)
    with tempfile.TemporaryDirectory(prefix='player-join-fixture-') as folder:
        fixture_hub(folder)  # writes a fixture-only config
        hub = Hub(folder)
        hub.config['player_join_base_url'] = 'http://qr-game.test:8163'
        for team, slugs in {'gamemaster': ['laser-tag-y'], 'green': ['mobile-ltz'], 'purple': ['mobile-ltz']}.items():
            sandbox = hub.sandboxes[team]
            sandbox.machines_dir = str(ROOT / 'sandboxes' / team / 'prototypes')
            for slug in slugs:
                sandbox._prototypes.append(sandbox._load_one(slug))
                sandbox._modules[slug].hub_init(HubContext(sandbox, slug))
            # Extra tabs are inert and intentionally enabled to verify hiding,
            # stale preferences, and the explicit show-other-tabs action.
            if team != 'gamemaster':
                for slug in ('ltx', 'ltz-score'):
                    sandbox._prototypes.insert(0, dict(slug=slug, name=slug, description='Fixture tab',
                        base=f'/p/{slug}', default_url=f'/p/{slug}/', pages=[]))
                    sandbox.app.add_url_rule(f'/p/{slug}/', slug, lambda: 'Other player tab')
        print('Player join fixture: http://127.0.0.1:8163', flush=True)
        make_server('127.0.0.1', 8163, hub.wsgi, threaded=True).serve_forever()
