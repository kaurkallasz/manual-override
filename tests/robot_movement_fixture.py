"""Synthetic robot positions for deterministic tests; no hardware commands."""
import math
import tempfile
import time
from unittest.mock import patch
from flask import jsonify, request
from werkzeug.serving import make_server


def observation(level, now, elapsed=0):
    samples = ((.1,.1),(.5,.1),(.9,.1),(.1,.9),(.5,.9),(.9,.9))
    def pose(side,u,v,z):
        return [100+1000*u,-300+600*v,-100+z,0] if side=='green' else [1100-1000*u,300-600*v,-95+z,0]
    camera = {'contract':'photon.board.camera-markers','version':1,'status':'ready','source':'camera',
              'coordinate_space':'corrected-camera-normalized','max_age_s':1.5,'frame_at':now,'width':1600,'height':900,
              'tags':[{'id':s['aruco_id'],'camera':[s.get('marker_x',s['x'])/level.width,s.get('marker_y',s['y'])/level.height],'last_seen':now} for s in level.sockets.values()]}
    if 'marker_x' in level.core:
        camera['tags'].append({'id':38,'camera':[level.core['marker_x']/level.width,level.core['marker_y']/level.height],'last_seen':now})
    relay = {'contract':'hhh.relay.arms','version':1,'status':'ready','arms':{}}
    cal = {'contract':'hhh.cal2.movement','version':1,'status':'ready','arms':{}}
    for side in ('green','purple'):
        device={'ip':'fixture-'+side}
        cal['arms'][side]={'status':'ready','revision':side+'-calibration','device':device,
                          'samples':[[u,v,*pose(side,u,v,0)[:3]] for u,v in samples]}
        offset=0 if side=='green' else math.pi
        u=.5+.34*math.cos(elapsed/31+offset);v=.5+.32*math.sin(elapsed/43+offset)
        z=65+45*math.sin(elapsed/17+offset)
        relay['arms'][side]={'connected':True,'feedback_ok':True,'feedback_at':now,'motion_epoch':1,'device':device,
                             'pose':pose(side,u,v,z)}
    return {'relay':relay,'calibration':cal,'camera':camera}


def seed(engine,duration=600):
    engine.stop_background()
    for i in range(duration+1):
        now=10000+i
        data=observation(engine.level,now,i)
        with patch('time.time',return_value=now):
            engine.robot_movement.observe(data,now,float(i))
    engine.sim_time=duration


def create_app(folder):
    from results_replay_fixture import create_results_app
    app,game=create_results_app(folder)
    owner=game._module('photon-progress');finalize=owner.finalize_attempt;pending={'value':False}
    def save(value):
        if pending['value']:raise ValueError('Fixture save temporarily unavailable')
        return finalize(value)
    owner.finalize_attempt=save

    @app.post('/__test/movement')
    def movement():
        event=game._progress.roster()['events']['active_id']
        app.test_client().post('/__test/camera',json={'enabled':True})
        game.apply_command({'action':'start','event_id':event,'starting_atoms':{'green':100,'purple':102}})
        e=game._engine
        with e.lock:
            seed(e)
            for i in range(30):
                e.sim_time=60+(i//10)*240
                e.rewards.killed({'enemy_type':'grunt','x':400+(i//10)*350,'y':250+(i//10)*170,'kill_owner':'green' if i%2 else 'purple'});e.kills+=1;e.next_enemy_id+=1
            e.sim_time=600
            e.phase='won';e.rewards.victory_method='center_stack'
            e.telemetry['core_health_at_stack']={'hp':e.core_hp,'max_hp':e.core_max_hp}
        pending['value']=bool((request.get_json(silent=True) or {}).get('pending'))
        try:game._progress.flush()
        except ValueError:
            if not pending['value']:raise
        game._live.bump()
        return jsonify(run_id=game._run_id)

    @app.post('/__test/movement-save')
    def saved():
        pending['value']=False;game._progress.flush();game._live.bump()
        return jsonify(ok=True)

    @app.post('/__test/movement-refresh')
    def refresh():
        game._live.bump()
        return jsonify(ok=True)
    return app,game


if __name__=='__main__':
    from test_result_save_isolation import isolated_helpers
    with tempfile.TemporaryDirectory() as folder:
        app,game=create_app(folder)
        server=make_server('127.0.0.1',8157,app,threaded=True)
        print('Movement fixture ready',flush=True)
        try:
            with isolated_helpers():server.serve_forever()
        finally:game.hub_stop();app.config['fixture_cleanup']()
