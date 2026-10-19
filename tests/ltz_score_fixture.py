"""Real shared pages, temporary score receipts and no connected hardware."""
import argparse
from pathlib import Path
import tempfile
import uuid
from flask import jsonify,request
from werkzeug.serving import make_server
from mobile_ltz_fixture import create_app

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8131);args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='ltz-score-') as folder:
        app,game=create_app(folder);progress=game._module('photon-progress');store=progress._store
        def finish():
            from photon_game_runtime import rewards
            from photon_game_runtime.engine import orc_schedule
            e=game._engine;e.start({'first_wave_delay_s':1500},reward_enabled=True)
            rule=e.rewards.rule
            run_id=uuid.uuid4().hex;game._run_id=run_id
            game._progress.begin({'run_id':run_id,'reward_enabled':True,'metadata':{'reward_rules':rule}})
            for kind,count in [('grunt',70),('runner',10),('breaker',20),('brute',5)]:
                for _ in range(count):e.rewards.killed({'enemy_type':kind})
            e.kills=105;e.sim_time=450;e.phase='won';e.rewards.victory_method='center_stack';e.telemetry['core_health_at_stack']={'hp':8000,'max_hp':10000}
            game._progress.flush()
        finished=False
        @app.post('/__test/result')
        def result():
            global finished
            if not finished:
                finish();finished=True
            return jsonify(ok=True)
        @app.post('/__test/calibration-view')
        def calibration():
            # Presentation fixture; no movement and no lesson completion.
            game._journey.state.update(phase='calibration',active_side='green',queue=['green','purple'],turn=0)
            return jsonify(ok=True)
        print(f'LTZ score fixture: http://127.0.0.1:{args.port}',flush=True)
        try:make_server('127.0.0.1',args.port,app,threaded=True).serve_forever()
        finally:game.hub_stop();app.config['fixture_cleanup']()
