"""Temporary Game + Y server for virtual-upgrade testing; no robot modules."""
from pathlib import Path
import tempfile
from flask import Flask, request
from werkzeug.serving import make_server
from test_photon_framework import load, FakeContext


def fixture_app(folder):
    level, game, view = load('photon-level'), load('photon-game'), load('laser-tag-y')
    folder = Path(folder)
    game._settings = game.SettingsStore(folder/'settings.json')
    game.LOG_PATH = str(folder/'runs.jsonl')
    game._progress = game.ProgressLink(game._module, lambda:game._engine, game._live.bump, folder/'pending.json')
    context = FakeContext({'photon-level':level, 'photon-game':game})
    game.hub_init(context)
    view.hub_init(context)
    game.apply_command({'action':'set_virtual','virtual_play':True})
    app = Flask('virtual-upgrade-fixture')
    @app.before_request
    def identity(): request.environ['hhh.roles'] = {'gamemaster'}
    for module, slug in [(level,'photon-level'),(game,'photon-game'),(view,'laser-tag-y')]:
        app.register_blueprint(module.bp, url_prefix=f'/s/gamemaster/p/{slug}')
    @app.route('/theme.css')
    def theme(): return '',200,{'Content-Type':'text/css'}
    return app,game,view


if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='virtual-upgrades-') as folder:
        app, game, view = fixture_app(folder)
        try:
            server = make_server('127.0.0.1',0,app,threaded=True)
            Path('/tmp/virtual-upgrades-port').write_text(str(server.server_port))
            print(f'Virtual-only fixture http://127.0.0.1:{server.server_port}',flush=True)
            server.serve_forever()
        finally:
            view.hub_stop();game.hub_stop()
