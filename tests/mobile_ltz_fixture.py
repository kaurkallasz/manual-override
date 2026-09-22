"""Serve the real mobile UI and virtual game using temporary data; no robots."""
import importlib.util
import argparse
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch
from flask import Flask, request, jsonify, abort
from werkzeug.serving import make_server
from test_photon_framework import load, FakeContext, ROOT

def create_app(folder):
    level=load('photon-level');game=load('photon-game');renderer=load('laser-tag-y')
    game._settings=game.SettingsStore(Path(folder)/'settings.json');game.LOG_PATH=str(Path(folder)/'runs.jsonl')
    game._hub_ctx=FakeContext({'photon-level':level,'laser-tag-y':renderer})
    game._sync_level();game._engine.set_virtual_play(True)
    # This is an explicit isolated practice run, not the user's active game.
    # Setup stays idle so touch checks cannot be interrupted by a lost core.
    path=ROOT/'sandboxes/green/prototypes/mobile-ltz/prototype.py'
    spec=importlib.util.spec_from_file_location('mobile_fixture_ui',path);ui=importlib.util.module_from_spec(spec);spec.loader.exec_module(ui)
    ui.hub_init(None)
    app=Flask('mobile-ltz-isolated')
    camera_state={'enabled':False,'stale':False}
    def observation():
        level_data=game.game_snapshot()['level']
        return dict(contract='photon.board.runtime',version=1,status='ready',source='camera',corrected=True,
            frame_at=time.time()-(10 if camera_state['stale'] else 0),width=1280,height=720,
            tags=[dict(id=s['aruco_id'],nx=.1+.8*s['marker_x']/level_data['width'],
                       ny=.05+.9*s['marker_y']/level_data['height'],missing=0,tracked=True) for s in level_data['sockets']])
    def camera_frame():
        import cv2
        import numpy as np
        frame=np.full((720,1280,3),(30,46,35),dtype=np.uint8)
        for tag in observation()['tags']:
            x,y=int(tag['nx']*1280),int(tag['ny']*720)
            cv2.rectangle(frame,(x-18,y-18),(x+18,y+18),(230,240,230),-1)
            cv2.putText(frame,str(tag['id']),(x-14,y+5),cv2.FONT_HERSHEY_SIMPLEX,.5,(0,0,0),1)
        return dict(contract='hhh.camera-frame',version=1,status='ready',coordinate_space='corrected-camera-normalized',
                    frame_at=time.time(),width=1280,height=720,jpeg=cv2.imencode('.jpg',frame)[1].tobytes())
    def camera_descriptor():
        return dict(contract='hhh.camera-preview',version=1,status='ready' if camera_state['enabled'] else 'unavailable',coordinate_space='corrected-camera-normalized')
    @app.post('/__test/camera')
    def test_camera():
        camera_state.update(request.get_json());game._engine.set_virtual_play(not camera_state['enabled'])
        return jsonify(ok=True)

    @app.before_request
    def identity():request.environ['hhh.roles']={'green','gamemaster'}
    @app.post('/__test/command')
    def virtual_command():
        # Exists only in this temporary, loopback-only test app.
        data=request.get_json(silent=True) or {}
        action=data.get('action')
        if action not in ('start','pause','resume','reset','virtual_test_loadout','place','loadout'):abort(400)
        return jsonify(game.apply_command({**data,'action':action,'virtual_play':True,'reward_enabled':False}))
    facade=load('mobile-ltz-api');facade.hub_init(FakeContext({'photon-game':game,'photon-level':level,'laser-tag-y':renderer, 'photon-board':SimpleNamespace(runtime_observation=observation),
        'camera-calibration':SimpleNamespace(preview_snapshot=camera_descriptor,preview_frame=camera_frame)}))
    renderer.hub_init(FakeContext({'photon-game':game,'photon-level':level}))
    app.register_blueprint(game.bp,url_prefix='/s/gamemaster/p/photon-game')
    app.register_blueprint(renderer.bp,url_prefix='/s/gamemaster/p/laser-tag-y')
    app.register_blueprint(facade.bp,url_prefix='/s/gamemaster/p/mobile-ltz-api')
    app.register_blueprint(ui.bp,url_prefix='/s/green/p/mobile-ltz')
    return app,game

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8117)
    port=parser.parse_args().port
    with tempfile.TemporaryDirectory(prefix='mobile-ltz-') as folder:
        app,game=create_app(folder);server=make_server('127.0.0.1',port,app,threaded=True)
        print(f'Mobile fixture http://127.0.0.1:{port}/s/green/p/mobile-ltz/',flush=True)
        try:server.serve_forever()
        finally:game.hub_stop()
