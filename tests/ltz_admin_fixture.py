"""Isolated Game Master practice flow; temporary players, fake hardware only."""
from pathlib import Path
import argparse
import tempfile
from werkzeug.serving import make_server
from mobile_ltz_fixture import create_app

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8133);args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='ltz-admin-') as folder:
        app,game=create_app(folder);progress=game._module('photon-progress')
        for side in ('green','purple'):progress.player_command(side,{'action':'select','player_id':'ltz-test-'+side})
        game._engine.set_virtual_test_loadout(None,None)
        game._presets=game.Presets(Path(folder)/'presets.json');game._presets.ensure_map(game._level_projection['name'],game._settings.snapshot())
        print(f'LTZ admin fixture: http://127.0.0.1:{args.port}',flush=True)
        try:make_server('127.0.0.1',args.port,app,threaded=True).serve_forever()
        finally:game.hub_stop();app.config['fixture_cleanup']()
