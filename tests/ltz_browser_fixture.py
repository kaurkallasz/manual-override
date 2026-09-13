"""Serve LTZ UI against a temporary real store; never connects to robots."""
import importlib.util
import json
from pathlib import Path
import tempfile
import uuid
from flask import Flask, jsonify, request, send_from_directory
from werkzeug.serving import make_server
from test_photon_framework import ROOT, load
from photon_performance_fixture import build_fixture


def fixture_app(folder):
    progress=load('photon-progress'); progress.DATA_DIR=Path(folder); progress.hub_init(None)
    store=progress._store
    player=store.create_player('Preview Pilot',uuid.uuid4().hex)['player_id']; store.select_player('green',player)
    for index in range(6):
        run_id=f'preview-{index}'
        store.begin({'run_id':run_id,'reward_enabled':True,'metadata':{'level_id':'z-pixel-first-map','settings_revision':1,'settings_hash':'demo','orc_schedule':{'total':3000}}})
        store.record({'run_id':run_id,'sequence':1,'kills':2000+index*100,'outcome':'won','active_seconds':180-index*10,'released_orcs':3000,'finished_at':1788192000+index*86400},final=True)
    for track in store.snapshot('green')['player']['levels']:
        for level in (2,3,4):
            p=store.snapshot('green')['player'];store.mutate_player('green',{'action':'purchase','track':track,'level':level,'revision':p['revision'],'operation_id':uuid.uuid4().hex})
    app=Flask('ltz-browser-isolated')
    @app.before_request
    def test_identity():request.environ['hhh.roles']={'gamemaster','green','purple'}
    app.register_blueprint(progress.bp,url_prefix='/s/gamemaster/p/photon-progress')
    for side in ('green','purple'):
        path=ROOT/f'sandboxes/{side}/prototypes/ltz-score/prototype.py'
        spec=importlib.util.spec_from_file_location(f'preview_{side}',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        app.register_blueprint(m.bp,url_prefix=f'/s/{side}/p/ltz-score')
    fixture=build_fixture(24)
    for i,tower in enumerate(fixture['towers']):tower['upgrade_level']=2+(i//4)%3
    for i,field in enumerate(fixture['connections']):field.update(upgrade_level=2+i%3,visual_width_px=9.5+1.5*(i%3),visual_state='combat',visible=True,provisional=False)
    fixture['phase']='running';fixture['paused']=True
    @app.route('/s/gamemaster/p/laser-tag-y/api/state')
    def state():return jsonify(fixture)
    @app.route('/s/gamemaster/p/photon-game/api/orc-preview',methods=['POST'])
    def preview():return jsonify(ok=True,previews=fixture['configuration']['orc_previews'])
    @app.route('/s/gamemaster/p/<module>/<path:file>')
    def assets(module,file):
        if module not in ('laser-tag-y','photon-level','photon-game'):return '',404
        if module=='laser-tag-y' and file=='game':file='index.html'
        if module=='laser-tag-y' and file=='screen':file='screen.html'
        return send_from_directory(ROOT/f'sandboxes/gamemaster/prototypes/{module}',file)
    @app.route('/theme.css')
    def theme():return '',200,{'Content-Type':'text/css'}
    return app,fixture


if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='ltz-browser-') as folder:
        app,fixture=fixture_app(folder)
        Path('/tmp/ltz-browser-scene.json').write_text(json.dumps(fixture))
        server=make_server('127.0.0.1',0,app,threaded=True)
        Path('/tmp/ltz-browser-port').write_text(str(server.server_port))
        print(f'Isolated fixture http://127.0.0.1:{server.server_port}',flush=True)
        server.serve_forever()
