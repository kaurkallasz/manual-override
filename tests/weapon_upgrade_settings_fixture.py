"""Isolated settings, score and mobile pages; temporary saves, no hardware."""
from pathlib import Path
import tempfile
from werkzeug.serving import make_server
from mobile_ltz_fixture import create_app


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='weapon-upgrades-') as folder:
        app, game = create_app(folder)
        game._presets = game.Presets(Path(folder) / 'level-presets.json')
        game._presets.ensure_map(game._level_projection['name'], game._settings.snapshot())
        server = make_server('127.0.0.1', 0, app, threaded=True)
        Path('/tmp/weapon-upgrade-settings-port').write_text(str(server.server_port))
        print(f'Upgrade settings fixture: http://127.0.0.1:{server.server_port}', flush=True)
        try:
            server.serve_forever()
        finally:
            game.hub_stop()
            app.config['fixture_cleanup']()
