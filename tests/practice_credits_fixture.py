"""Saved practice loss in real player pages; temporary wallets, no robots."""
from pathlib import Path
import tempfile
from werkzeug.serving import make_server
from mobile_ltz_fixture import create_app

if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='practice-credits-') as folder:
        app,game=create_app(folder);game._engine.stop_background()
        game._engine.set_virtual_test_loadout(None,None)
        progress=game._module('photon-progress')
        progress.player_command('purple',{'action':'select','player_id':'ltz-test-purple'})
        game.apply_command({'action':'start','virtual_play':True,'reward_enabled':False})
        e=game._engine
        for kind,count in [('grunt',356),('runner',171),('breaker',134),('brute',9)]:
            for _ in range(count):e.rewards.killed({'enemy_type':kind})
        e.kills=670;e.sim_time=1193;e.core_hp=0;e.phase='overrun';game._progress.flush();game._journey.tick()
        server=make_server('127.0.0.1',0,app,threaded=True)
        Path('/tmp/practice-credits-port').write_text(str(server.server_port))
        print(f'Practice credit fixture: http://127.0.0.1:{server.server_port}',flush=True)
        try:server.serve_forever()
        finally:game.hub_stop();app.config['fixture_cleanup']()
