"""Real player UI with a deterministic test clock; temporary profiles, no hardware."""
from pathlib import Path
import tempfile
from flask import request
from werkzeug.serving import make_server
from mobile_ltz_fixture import create_app


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='mission-countdown-') as folder:
        app, game = create_app(folder)
        game._engine.stop_background()
        game._engine.set_virtual_test_loadout(None, None)
        game._module('photon-progress').player_command('green', {'action':'select', 'player_id':None})

        @app.post('/__test/tick')
        def tick():
            count = int(request.get_json().get('ticks', 0))
            assert 0 <= count <= 200
            for _ in range(count):
                game._engine.step(.05)
            game._live.bump()
            return {'ok':True}

        server = make_server('127.0.0.1', 0, app, threaded=True)
        Path('/tmp/mission-countdown-port').write_text(str(server.server_port))
        try:
            server.serve_forever()
        finally:
            game.hub_stop()
            app.config['fixture_cleanup']()
