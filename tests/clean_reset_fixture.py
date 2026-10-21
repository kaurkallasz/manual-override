"""Loopback-only browser fixture: real Hub/Game/Progress, simulated hardware."""
import re
import tempfile
from flask import jsonify, request
from werkzeug.serving import make_server
from mobile_ltz_fixture import create_app
from test_player_join import fixture_hub
from test_clean_reset import attach_management
from hub import Hub


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='clean-reset-fixture-') as folder:
        fixture_hub(folder)
        hub = Hub(folder)
        hub.config['player_join_base_url'] = 'http://qr-game.test:8164'
        app, game = create_app(folder)
        try:
            for name, blueprint in app.blueprints.items():
                rule = next(rule for rule in app.url_map.iter_rules() if rule.endpoint.startswith(name+'.'))
                match = re.match(r'/s/([^/]+)/p/([^/]+)', rule.rule)
                if not match: continue
                team, slug = match.groups();sandbox = hub.sandboxes[team]
                sandbox.app.register_blueprint(blueprint, url_prefix='/p/'+slug)
                sandbox._modules[slug] = object()
                sandbox._prototypes.append(dict(slug=slug, name=slug, description='Fixture', base='/p/'+slug,
                    default_url='/p/'+slug+'/', pages=[]))
            attach_management(hub, game)
            fail = {'stop':False}
            relay = game._module('dobot-mg400-relay')
            stopped = relay.stop_side
            relay.stop_side = lambda side: dict(contract='hhh.relay.stop',version=1,status='unavailable',stopped=False) if fail['stop'] else stopped(side)
            # Make both arms connected for a meaningful simulated stop failure.
            app.test_client().post('/__test/camera', json={'enabled': True})
            @hub.root_app.post('/__test/stop-failure')
            def stop_failure():
                fail['stop'] = bool(request.json['enabled'])
                return jsonify(ok=True)
            print('Clean reset fixture: http://127.0.0.1:8164', flush=True)
            make_server('127.0.0.1', 8164, hub.wsgi, threaded=True).serve_forever()
        finally:
            game.hub_stop();app.config['fixture_cleanup']()
