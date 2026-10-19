"""Loopback-only results demo backed by real Game/Progress, temporary players."""
import tempfile
import time
import uuid
from flask import jsonify, request
from werkzeug.serving import make_server
from mobile_ltz_fixture import create_app


def create_results_app(folder):
    app,game=create_app(folder)
    progress=game._module('photon-progress')
    event=progress.progress_snapshot()['events']['active_id']

    def command(action,**value):
        return game.apply_command({'action':action,'event_id':event,'run_id':game._run_id,**value})

    def start():
        return command('start',starting_atoms={'green':100,'purple':102})

    def finish(kills,outcome='overrun'):
        e=game._engine
        with e.lock:
            # Deliberate fixture evidence; never exposed by the production app.
            for i in range(kills):
                owner='green' if i%6<3 else 'purple' if i%6<5 else 'shared'
                enemy={'enemy_type':'grunt','hp':1}
                e._hurt_enemy(enemy,1,owner);e.rewards.killed(enemy)
            e.kills=kills;e.sim_time=154.8;e.next_enemy_id=kills+1
            if outcome=='won':
                e.rewards.victory_method='center_stack'
                e.telemetry['core_health_at_stack']={'hp':e.core_hp,'max_hp':e.core_max_hp}
            e.phase=outcome
        game._progress.flush();game._live.bump()
        return progress.public_snapshot('green')

    def pair(names):
        game.saved_game_command('green',{'action':'new','event_id':event,'operation_id':uuid.uuid4().hex})
        for side,name in zip(('green','purple'),names):
            progress.player_command(side,{'action':'create','event_id':event,'name':name,'select':True,'operation_id':uuid.uuid4().hex})

    @app.post('/__test/seed-results')
    def seed_results():
        app.test_client().post('/__test/camera',json={'enabled':True})
        start();finish(700);command('next_match')
        pair(('Leo','Nora'));start();finish(1100);command('next_match')
        pair(('Ari','Mira'))
        for n in (250,500):
            start();finish(n);command('next_match')
        start()
        return jsonify(ok=True,event_id=event)

    @app.post('/__test/finish-level')
    def finish_level():
        return jsonify(finish(900,'won'))

    return app,game


if __name__=='__main__':
    with tempfile.TemporaryDirectory() as folder:
        app,game=create_results_app(folder)
        server=make_server('127.0.0.1',8139,app,threaded=True)
        print('Results fixture http://127.0.0.1:8139',flush=True)
        try:server.serve_forever()
        finally:game.hub_stop();app.config['fixture_cleanup']()
