"""Isolated Y/Game with synthetic camera markers/occupancy; no robot modules."""
from pathlib import Path
from types import SimpleNamespace
import base64
import tempfile
import time
from flask import request
from werkzeug.serving import make_server
from virtual_upgrades_fixture import fixture_app


def start_core_ring(engine, scored=True):
    """Prepare a real eight-turret ring in the isolated test simulation."""
    engine.reset()
    for index, marker in enumerate((41, 43, 42, 45, 54, 46, 52, 53)):
        engine.operator_turret_command('operator_atom', engine.level.socket_by_marker[marker],
                                      100 if index % 2 == 0 else 102)
    engine.start(reward_enabled=scored)


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='operator-turrets-') as folder:
        app, game, view = fixture_app(folder)
        relation = None
        camera = dict(enabled=True, width=1280, height=720, dx=0, dy=0, image='')

        def tags():
            now = time.time()
            result = []
            level = game._engine.level
            for socket in [*level.sockets.values(), {**level.core, 'aruco_id': 38}]:
                x = socket.get('marker_x', socket['x']) / level.width + camera['dx']
                y = socket.get('marker_y', socket['y']) / level.height + camera['dy']
                radius_x, radius_y = 15 / camera['width'], 15 / camera['height']
                result.append(dict(id=socket['aruco_id'], camera=[x, y], last_seen=now, visible=True,
                    corners=[[x-radius_x,y-radius_y],[x+radius_x,y-radius_y],[x+radius_x,y+radius_y],[x-radius_x,y+radius_y]]))
            return result

        def tracking():
            return dict(contract='photon.board.tracking', version=1, status='ready', tags=tags())

        def markers():
            return dict(contract='photon.board.camera-markers', version=1,
                status='ready' if camera['enabled'] else 'unavailable', source='camera',
                coordinate_space='corrected-camera-normalized', width=camera['width'], height=camera['height'],
                frame_at=time.time(), max_age_s=1.5, tags=tags() if camera['enabled'] else [])

        def preview():
            if not camera['enabled']:
                return dict(contract='photon.board.preview', version=1, status='unavailable')
            return dict(contract='photon.board.preview', version=1, status='ready',
                        coordinate_space='corrected-camera-normalized', width=camera['width'], height=camera['height'],
                        frame_at=time.time(), jpeg=base64.b64decode(camera['image']))

        view._hub_ctx.modules['photon-board'] = SimpleNamespace(
            tracking_snapshot=tracking, camera_markers_snapshot=markers, preview_frame=preview)

        def observation():
            game._set_input('board', status='ready' if camera['enabled'] else 'unavailable',
                            source='camera', upstream={'source': 'camera'})
            return {'status': 'ready', 'sampled_at': time.time(), 'relations': [],
                    'occupancy': {'status': 'ready', 'sampled_at': time.time(),
                                  'relations': [relation] if relation else []}}

        game._physical_observation = observation
        game._engine.set_physical_source(observation)

        @app.post('/fixture/start')
        def start():
            global relation
            relation = None
            scored = request.get_json().get('scored', False)
            game._engine.set_virtual_play(False)
            game._engine.start(reward_enabled=scored)
            game._engine.ingest_physical(observation())
            # Exercise the scored-run UI/API guards without a real roster,
            # score persistence, arms or other hardware modules.
            game._progress._set(reward_enabled=scored)
            return {'ok': True}

        @app.post('/fixture/physical')
        def physical():
            global relation
            value = request.get_json()
            tag = value.get('tag')
            sid = value.get('socket_id', 'socket_01')
            relation = None if tag is None else {
                'movable_id': tag, 'marker_id': game._engine.level.sockets[sid]['aruco_id'],
                'relation_id': f'{tag}:{sid}', 'state': value.get('state', 'present'),
                'departed_at': time.time() if value.get('state') == 'departed' else None,
            }
            game._engine.set_virtual_play(False)
            game._engine.ingest_physical(observation())
            return {'ok': True}

        @app.post('/fixture/core-ring')
        def core_ring():
            global relation
            relation = None
            scored = request.get_json().get('scored', False)
            start_core_ring(game._engine, scored)
            game._engine.set_virtual_play(False)
            game._engine.ingest_physical(observation())
            game._progress._set(reward_enabled=scored)
            return {'ok': True}

        @app.get('/fixture/camera-layout')
        def camera_layout():
            return dict(width=camera['width'], height=camera['height'], tags=tags())

        @app.post('/fixture/camera')
        def camera_config():
            camera.update(request.get_json())
            game._engine.ingest_physical(observation())
            return {'ok': True}

        try:
            server = make_server('127.0.0.1', 0, app, threaded=True)
            Path('/tmp/operator-turrets-port').write_text(str(server.server_port))
            print(f'Operator fixture: http://127.0.0.1:{server.server_port}', flush=True)
            server.serve_forever()
        finally:
            view.hub_stop()
            game.hub_stop()
