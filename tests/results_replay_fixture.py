"""Loopback-only campaign end/replay browser fixture; temporary data, fake arms."""
import tempfile
from flask import jsonify
from werkzeug.serving import make_server
from mobile_ltz_fixture import create_app
from test_control_journey import CalFixture
from test_result_save_isolation import isolated_helpers


def create_results_app(folder):
    app,game=create_app(folder)
    game._engine.stop_background()
    event=game._progress.roster()['events']['active_id']
    owner=game._module('photon-progress')
    finalize=owner.finalize_attempt
    save_fault={'blocked':False}
    def finalize_with_fault(value):
        if save_fault['blocked']:raise ValueError('Save temporarily unavailable')
        return finalize(value)
    owner.finalize_attempt=finalize_with_fault

    def finish(kills=35,outcome='won'):
        e=game._engine
        with e.lock:
            for i in range(kills):
                enemy={'enemy_type':'grunt','hp':0,'x':400 if i<30 else 1200,'y':250 if i<30 else 700,
                       'kill_owner':'green' if i%2 else 'purple'}
                e.rewards.killed(enemy);e.kills+=1;e.next_enemy_id+=1
            e.phase=outcome;e.sim_time=140
            e.rewards.victory_method='center_stack' if outcome=='won' else None
            e.telemetry['core_health_at_stack']={'hp':e.core_hp,'max_hp':e.core_max_hp}
        game._progress.flush();game._live.bump()
        return game.game_snapshot()

    @app.post('/__test/final-level')
    def final_level():
        app.test_client().post('/__test/camera',json={'enabled':True})
        game.apply_command({'action':'start','event_id':event,'starting_atoms':{'green':100,'purple':102}})
        game._hub_ctx.modules['auto-pickup-game']=CalFixture()
        for _ in range(3):
            finish(0);run=game._run_id
            for side in ('green','purple'):
                game.mobile_journey_command(side,{'action':'ready','event_id':event,'run_id':run})
            if game._journey.snapshot()['phase']=='calibration':
                for side in ('green','purple'):game.mobile_journey_command(side,{'action':'complete'})
        return jsonify(finish())

    @app.post('/__test/finish')
    def finish_route():return jsonify(finish(0))

    @app.post('/__test/finish-pending')
    def finish_pending():
        save_fault['blocked']=True
        try:finish()
        except ValueError:pass
        game._live.bump()
        return jsonify(game.game_snapshot())

    @app.post('/__test/retry-save')
    def retry_save():
        save_fault['blocked']=False
        game._progress.flush();game._live.bump()
        return jsonify(game.game_snapshot())

    @app.post('/__test/ring/<action>')
    def ring(action):
        e=game._engine
        with e.lock:
            if action=='complete':
                for i,marker in enumerate((41,43,42,45,54,46,52,53)):
                    e.operator_turret_command('operator_atom',e.level.socket_by_marker[marker],100 if i%2==0 else 102)
            else:
                field=next(f for f in e.force_fields.values() if f.get('ring_boundary'))
                field['broken']=action=='break';e._evaluate_ring_topology()
        game._live.bump();return jsonify(game.game_snapshot())

    return app,game


if __name__=='__main__':
    with tempfile.TemporaryDirectory() as folder:
        app,game=create_results_app(folder)
        server=make_server('127.0.0.1',8142,app,threaded=True)
        print('Replay fixture http://127.0.0.1:8142',flush=True)
        try:
            with isolated_helpers():server.serve_forever()
        finally:game.hub_stop();app.config['fixture_cleanup']()
