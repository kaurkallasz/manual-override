"""Real Y/Mobile pages with isolated practice data and a repeatable archer scene."""
import argparse
import tempfile
from mobile_ltz_fixture import create_app
from werkzeug.serving import make_server

parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8129)
port=parser.parse_args().port
with tempfile.TemporaryDirectory(prefix='ranged-breaker-') as folder:
    app,game=create_app(folder)
    e=game._engine
    with e.lock:
        e.set_virtual_test_loadout(dict.fromkeys(('damage-machine-gun','damage-flamethrower','damage-mortar','damage-tesla-coil','forcefield'),4))
        for i,sid in enumerate(e.level.sockets):e.place(100+i%4,sid,source='virtual')
        e.start({'breaker_attack_mode':'ranged','first_wave_delay_s':1500,'enemy_health_multiplier':10,'core_hp':100000})
        for i in range(36):
            assert e._spawn_enemy('breaker',{})
            enemy=e.enemies[e.next_enemy_id-1]
            enemy.update(x=130+(i%12)*128,y=100+(i//12)*360,hp=100000,max_hp=100000,next_scan_at=0)
        for tower in e.placements.values():tower.update(hp=100000,max_hp=100000)
    print(f'Archer fixture: http://127.0.0.1:{port}/s/green/p/mobile-ltz/',flush=True)
    try:make_server('127.0.0.1',port,app,threaded=True).serve_forever()
    finally:game.hub_stop();app.config['fixture_cleanup']()
