"""Loopback-only visual fixture. All progress, camera and arms are temporary/fake."""
from pathlib import Path
import tempfile
from flask import request, jsonify
from werkzeug.serving import make_server
from mobile_ltz_fixture import create_app


def fixture(folder):
    app, game = create_app(folder)
    game._engine.stop_background()

    @app.post('/__test/starters')
    def starters():
        data=request.get_json() or {};level=int(data.get('level',1));e=game._engine
        with e.lock:
            e.reset();e.set_virtual_play(True)
            players={side:{'control_tier':level,'levels':dict.fromkeys(
                ('damage-machine-gun','damage-flamethrower','damage-mortar','damage-tesla-coil','forcefield'),level)}
                for side in ('green','purple')}
            e.start({'first_wave_delay_s':1500},progression=players,event_game={'level':level,'atoms':{'green':{'tag':100},'purple':{'tag':102}}})
            game._run_id='starter-visual-'+str(level)
            if data.get('full_board'):
                for i,sid in enumerate(e.level.sockets):e.place(100+i%4,sid,source='virtual')
            e.runtime_time=e.sim_time=10
        game._live.bump()
        return jsonify(game.game_snapshot())

    @app.post('/__test/destroy-starter')
    def destroy():
        e=game._engine
        with e.lock:
            t=e.starter_turrets['starter_green_1'];e._apply_tower_damage(t,t['hp'])
            e._after_tower_destruction();e.runtime_time=e.sim_time=15
        game._live.bump()
        return jsonify(game.game_snapshot())

    return app,game


if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='starter-defenses-') as folder:
        app,game=fixture(folder)
        server=make_server('127.0.0.1',0,app,threaded=True)
        Path('/tmp/starter-defenses-port').write_text(str(server.server_port))
        print(f'Starter fixture http://127.0.0.1:{server.server_port}',flush=True)
        try:server.serve_forever()
        finally:game.hub_stop();app.config['fixture_cleanup']()
