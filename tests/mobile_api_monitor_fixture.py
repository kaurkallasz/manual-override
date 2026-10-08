"""Loopback-only Mobile LTZ monitor fixture: fake state, no robot modules."""
import argparse
import copy
import time
from types import SimpleNamespace
from flask import Flask, jsonify, request

from test_photon_framework import FakeContext, load


def create_app():
    facade = load('mobile-ltz-api')
    counts = {'snapshots': 0, 'commands': 0}
    state = {'contract': 'photon.game', 'version': 2, 'status': 'ready',
             'virtual_play': True, 'phase': 'running', 'run_id': 'monitor-fixture',
             'level_revision': 19, 'level': {'name': 'Photon yard', 'width': 1696, 'height': 960},
             'settings': {'wave_count': 8}, 'presentation': {'revision': 'fixture'},
             'wave': 3, 'core_hp': 240, 'core_max_hp': 240, 'kills': 37,
             'journey': {'phase': 'playing'},
             'mobile_arms': {side: {'side': side, 'connected': False} for side in ('green', 'purple')},
             'enemies': [{'id': i, 'enemy_type': 'grunt', 'x': i * 19.3, 'y': 320,
                          'hp': 35, 'max_hp': 40, 'vx': 8, 'vy': 0} for i in range(24)]}
    def snapshot():
        counts['snapshots'] += 1
        return {**copy.deepcopy(state), 'server_time': time.time()}
    def command(data):
        counts['commands'] += 1
        raise ValueError('No controls in the diagnostic fixture')
    facade.hub_init(FakeContext({'photon-game': SimpleNamespace(game_snapshot=snapshot, mobile_command=command)}))
    app = Flask('mobile-api-monitor-fixture')
    @app.before_request
    def identity():
        request.environ['hhh.roles'] = {'gamemaster', 'green', 'purple'}
    @app.get('/__test/counts')
    def counters():
        return jsonify(counts)
    app.register_blueprint(facade.bp, url_prefix='/s/gamemaster/p/mobile-ltz-api')
    return app


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8124)
    args = parser.parse_args()
    create_app().run(host='127.0.0.1', port=args.port, threaded=True, use_reloader=False)
