"""Real event/calibration owners at Purple's partial L3 lesson; fake devices only."""
import os
import tempfile
import time
from flask import jsonify, request
from werkzeug.serving import make_server
from mobile_ltz_fixture import create_app


def prepare(app, game):
    client=app.test_client()
    client.post('/__test/camera',json={'enabled':True})
    event=game._progress.roster()['events']['active_id']
    game.apply_command({'action':'start','event_id':event,'starting_atoms':{'green':100,'purple':102}})
    for _ in range(2):
        with game._engine.lock:
            game._engine.phase='won'
            game._engine.rewards.victory_method='center_stack'
            game._engine.telemetry['core_health_at_stack']={'hp':game._engine.core_hp,'max_hp':game._engine.core_max_hp}
        game._progress.flush()
        for side in ('green','purple'):
            game.mobile_journey_command(side,{'action':'ready','event_id':event,'run_id':game._run_id})
    def wait_for(side):
        for _ in range(100):
            game._journey_tick()
            cal=game._module('auto-pickup-game').calibration_session_snapshot()
            if cal.get('active_side')==side and cal.get('marker_preparation',{}).get('ready'):
                return cal['sessions'][cal['active_id']]
            time.sleep(.05)
        raise AssertionError(game._journey.snapshot())
    wait_for('green')
    for marker in range(30,36):
        game.mobile_journey_command('green',{'action':'capture','marker':marker})
    owner=game._module('auto-pickup-game')
    state=owner.calibration_session_snapshot()
    points=state['sessions'][state['active_id']]['draft']['points']
    for marker in (31,35,33,34):
        camera=next(p['camera'] for p in points.values() if p['marker']==marker)
        game.mobile_journey_command('green',{'action':'raised','marker':marker,'camera':camera})
    game.mobile_journey_command('green',{'action':'complete'})
    client.post('/s/purple/p/cartesian-xyz-test/api/enable',json={})
    session=wait_for('purple')
    game.mobile_journey_command('purple',{'action':'capture','marker':30})
    return {'event_id':event,'game_id':game._progress.roster()['saved_games']['active_id'],
            'session_id':session['id']}


if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='reset-calibration-') as folder:
        app,game=create_app(folder)
        blocked={'value':False}
        relay=game._module('dobot-mg400-relay')
        stop=relay.stop_side
        relay.stop_side=lambda side: ({'contract':'hhh.relay.stop','version':1,'status':'unavailable','stopped':False}
                                     if blocked['value'] else stop(side))
        @app.post('/__test/reset-stop')
        def stop_feedback():
            blocked['value']=request.get_json()['blocked']
            return jsonify(ok=True)
        @app.get('/__test/reset-calibration-seed')
        def snapshot():return jsonify(seed)
        seed=prepare(app,game)
        if os.environ.get('LTZ_CALIBRATION_LEGACY')=='1':
            game._journey.checkpoint_calibration=lambda roster:None
        server=make_server('127.0.0.1',8148,app,threaded=True)
        print('Reset calibration fixture http://127.0.0.1:8148',flush=True)
        try:server.serve_forever()
        finally:game.hub_stop();app.config['fixture_cleanup']()
