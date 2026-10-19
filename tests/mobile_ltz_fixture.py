"""Serve the real mobile UI and virtual game using temporary data; no robots."""
import importlib.util
import argparse
from pathlib import Path
import tempfile
import shutil
import sys
import time
import uuid
from types import SimpleNamespace
from unittest.mock import patch
from flask import Flask, request, jsonify, abort, Response
from werkzeug.serving import make_server
from test_photon_framework import load, FakeContext, ROOT

def create_app(folder, *, virtual_controls=False):
    level=load('photon-level');game=load('photon-game');renderer=load('laser-tag-y');board=load('photon-board')
    progress=load('photon-progress');progress.DATA_DIR=Path(folder)/'progress';progress.hub_init(None)
    event_id=progress.event_command({'action':'create','name':'Fixture event','operation_id':'fixture-event'})['result']['event_id']
    for side in ('green','purple'):
        player=progress.player_command(side,{'action':'create','name':side+' pilot','operation_id':uuid.uuid4().hex,'event_id':event_id})['result']['player_id']
        progress.player_command(side,{'action':'select','player_id':player,'event_id':event_id})
    game._settings=game.SettingsStore(Path(folder)/'settings.json');game.LOG_PATH=str(Path(folder)/'runs.jsonl')
    modules={'photon-level':level,'laser-tag-y':renderer,'photon-progress':progress}
    game._hub_ctx=FakeContext(modules)
    game._journey=game.Journey(Path(folder)/'journey.json',game._module,game._live.bump)
    game._progress=game.ProgressLink(game._module,lambda:game._engine,game._live.bump,Path(folder)/'pending.json',game._result_committed,game._journey_tick)
    game._sync_level();game._engine.set_virtual_play(True);game._engine.set_virtual_test_loadout(None,1)
    if virtual_controls:
        # Explicit test-only adapter: production no longer exposes virtual arm
        # commands. Exercise the retained simulation without restoring that API.
        def simulated_command(data):
            with game._engine.lock:
                return game._engine.mobile_arms[data['side']].command(data, game._engine)
        game.mobile_command = simulated_command
        profile_snapshot = progress.public_snapshot
        def simulated_profile(side):
            value = profile_snapshot(side)
            if value.get('player'):
                value['player'] = {**value['player'], 'current_control_tier':game._engine.virtual_test_control or 1}
            return value
        progress.public_snapshot = simulated_profile
        journey_snapshot = game.journey_snapshot
        game.journey_snapshot = lambda: {**journey_snapshot(), 'phase':'playing'}
    # This is an explicit isolated practice run, not the user's active game.
    # Setup stays idle so touch checks cannot be interrupted by a lost core.
    path=ROOT/'sandboxes/green/prototypes/mobile-ltz/prototype.py'
    spec=importlib.util.spec_from_file_location('mobile_fixture_ui',path);ui=importlib.util.module_from_spec(spec);spec.loader.exec_module(ui)
    ui.hub_init(None)
    purple_path=ROOT/'sandboxes/purple/prototypes/mobile-ltz/prototype.py'
    purple_spec=importlib.util.spec_from_file_location('purple_fixture_ui',purple_path)
    purple_ui=importlib.util.module_from_spec(purple_spec);purple_spec.loader.exec_module(purple_ui)
    purple_ui.hub_init(None)
    app=Flask('mobile-ltz-isolated')
    camera_state={'enabled':False,'stale':False}
    def observation():
        level_data=game._level_projection
        targets=([dict(id=a['marker'],nx=.5+a['x']/(16*1280/720),ny=.5+a['z']/16,missing=0,tracked=True) for a in field.list_areas()] if game._journey.snapshot()['phase']=='calibration' else [dict(id=s['aruco_id'],nx=.1+.8*s['marker_x']/level_data['width'],ny=.05+.9*s['marker_y']/level_data['height'],missing=0,tracked=True) for s in level_data['sockets']])
        hidden=set(camera_state.get('hidden_markers',[]))
        if game._journey.snapshot()['phase']=='calibration':hidden.update(a['marker'] for a in field.list_areas() if a.get('show_aruco') is False)
        targets=[t for t in targets if t['id'] not in hidden]
        for tag in targets:
            size=camera_state.get('marker_sizes',{}).get(str(tag['id']),36)
            tag['ncorners']=[[tag['nx']+dx*size/1280,tag['ny']+dy*size/720]
                             for dx,dy in ((-.5,-.5),(.5,-.5),(.5,.5),(-.5,.5))]
        return dict(contract='photon.board.runtime',version=1,status='ready' if not camera_state['stale'] else 'unavailable',error='camera stale' if camera_state['stale'] else None,source='camera',corrected=True,revision=1,observed_at=time.time(),
            placement=dict(contract='photon.board.placement',version=1,status='ready',sampled_at=time.time(),source_epoch='fixture',revision=1,relations=[]),
            frame_at=time.time()-(10 if camera_state['stale'] else camera_state.get('delay',0)),width=camera_state.get('width',1280),height=camera_state.get('height',720),
            tags=[] if camera_state.get('qualifying') else targets,
            detections=targets,visible_ids=[t['id'] for t in targets])
    board.runtime_observation=observation
    # This fixture supplies empty physical relationships, with explicit scope
    # acknowledgement matching the production Board/Game contract.
    board.game_observation=lambda *,scope,fixed_ids:dict(observation(),layout_scope=scope,fixed_ids=sorted(fixed_ids))
    def camera_frame(**options):
        import cv2
        import numpy as np
        frame=np.full((720,1280,3),(30,46,35),dtype=np.uint8)
        saved={a['marker'] for a in field.list_areas() if a['color']=='#33ff88' and a.get('show_area') and a.get('glow',0)>0}
        for tag in observation()['detections']:
            x,y=int(tag['nx']*1280),int(tag['ny']*720)
            if tag['id'] in saved:cv2.rectangle(frame,(x-23,y-23),(x+23,y+23),(70,235,85),3)
            half=int(camera_state.get('marker_sizes',{}).get(str(tag['id']),36)/2)
            cv2.rectangle(frame,(x-half,y-half),(x+half,y+half),(230,240,230),-1)
            cv2.putText(frame,str(tag['id']),(x-14,y+5),cv2.FONT_HERSHEY_SIMPLEX,.5,(0,0,0),1)
        return dict(contract='hhh.camera-frame',version=1,status='ready',coordinate_space='corrected-camera-normalized',
                    frame_at=time.time(),width=camera_state.get('width',1280),height=camera_state.get('height',720),
                    jpeg=cv2.imencode('.jpg',cv2.resize(frame,(1920,1080)) if camera_state.get('width',1280)>1920 else frame)[1].tobytes())
    def camera_descriptor():
        return dict(contract='hhh.camera-preview',version=1,status='ready' if camera_state['enabled'] else 'unavailable',coordinate_space='corrected-camera-normalized')
    board._hub_ctx=FakeContext({'camera-calibration':SimpleNamespace(preview_frame=lambda:camera_frame() if camera_state['enabled'] and not camera_state['stale'] else dict(contract='hhh.camera-frame',version=1,status='unavailable',error='Camera unavailable'))})
    @app.get('/s/gamemaster/p/photon-board/api/preview')
    def operator_preview():
        if not camera_state['enabled'] or camera_state['stale']:
            return jsonify(error='Camera unavailable'),503
        def stream():
            while camera_state['enabled'] and not camera_state['stale']:
                frame=camera_frame()['jpeg']
                yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n'+frame+b'\r\n'
                time.sleep(.15)
        return Response(stream(),mimetype='multipart/x-mixed-replace; boundary=frame')
    @app.post('/__test/camera')
    def test_camera():
        camera_state.update(request.get_json());game._engine.set_virtual_play(not camera_state['enabled'])
        return jsonify(ok=True)

    @app.before_request
    def identity():request.environ['hhh.roles']={'green','purple','gamemaster'}
    @app.post('/__test/command')
    def virtual_command():
        # Exists only in this temporary, loopback-only test app.
        data=request.get_json(silent=True) or {}
        action=data.get('action')
        if action not in ('start','pause','resume','reset','virtual_test_loadout','place','loadout'):abort(400)
        if virtual_controls and action == 'virtual_test_loadout':
            game._engine.set_virtual_test_loadout(data.get('levels'), data.get('control'))
            return jsonify(game.game_snapshot())
        return jsonify(game.apply_command({**data,'action':action,'virtual_play':True,'reward_enabled':False}))
    # Actual target/layout owners with temporary files and measured fake inputs.
    field=load('playfield-areas');field_dir=Path(folder)/'playfield';field_dir.mkdir()
    shutil.copyfile(Path(field.HERE)/'screen.html',field_dir/'screen.html')
    field.HERE=str(field_dir);field.SETTINGS_PATH=str(field_dir/'settings.json');field.AREAS_PATH=str(field_dir/'areas.json')
    owner=load('auto-pickup-game');owner._lessons=owner.LessonStore(Path(folder)/'lessons.json')
    owner.CALIBRATION2_PATH=str(Path(folder)/'calibration2.json')
    owner._calibration2=owner._default_calibration2()
    @app.post('/__test/saved-calibrations')
    def saved_calibrations():
        from saved_calibration_fixture import seed
        seed(owner)
        return jsonify(ok=True)
    calibration_feedback={'connected':True}
    arm_enabled={'green':True,'purple':True}
    def disable_calibration_arm(side):
        arm_enabled[side]=False
        return dict(contract='hhh.relay.disabled',version=1,status='ready',inhibited=True,
                    connected=calibration_feedback['connected'],disabled=calibration_feedback['connected'])
    @app.post('/__test/calibration-feedback')
    def calibration_feedback_control():
        calibration_feedback.update(request.get_json());return jsonify(ok=True)
    @app.post('/__test/calibration-milestone')
    def calibration_milestone():
        # Real progression APIs, isolated profiles: three Joint and three XYZ wins.
        game._engine.set_virtual_test_loadout(None,None)
        for _ in range(6):
            run_id=uuid.uuid4().hex
            progress.begin_attempt({'run_id':run_id,'reward_enabled':True,'metadata':{}})
            attempt=progress.finalize_attempt({'run_id':run_id,'sequence':1,'kills':100,
                'outcome':'won','active_seconds':1500,'finished_at':time.time(),'released_orcs':100})['attempt']
        game._journey.result(attempt)
        game._journey.tick()
        return jsonify(ok=True,journey=game._journey.snapshot())
    @app.post('/__test/calibration-restart')
    def calibration_restart():
        previous=owner._lessons.snapshot().get('active_id')
        owner._lessons=owner.LessonStore(Path(folder)/'lessons.json')
        if (request.get_json(silent=True) or {}).get('legacy_active_id'):
            owner._lessons.state['active_id']=previous
        return jsonify(ok=True)
    measured_marker=[None]
    def measured_pose():
        target=next((a for a in field.list_areas() if a['marker']==measured_marker[0]),None)
        u,v=(.5+target['x']/(16*1280/720),.5+target['z']/16) if target else (.5,.5)
        return [260+100*u,-80+160*v,calibration_feedback.get('z',10),0]
    owner._hub_ctx=FakeContext({'playfield-areas':field,
      'webcam':SimpleNamespace(tag_snapshot=lambda:dict(contract='hhh.webcam.tags',version=1,status='ready',frame_at=observation()['frame_at'],width=1280,height=720,tags=observation()['tags'],detections=observation()['tags'])),
      'camera-calibration':SimpleNamespace(corrected_tag_snapshot=lambda tags,detections:dict(contract='hhh.camera-correction',version=1,status='ready',corrected=True,calibration_revision=camera_state.get('calibration_revision','fixture'),tags=tags,detections=detections)),
      'dobot-mg400-relay':SimpleNamespace(
        arms_snapshot=lambda:dict(contract='hhh.relay.arms',version=1,status='ready',observed_at=time.time(),arms={side:dict(connected=calibration_feedback['connected'],enabled=arm_enabled[side],feedback_at=time.time(),pose=measured_pose(),device={'ip':'fixture'}) for side in ('green','purple')}),
        disable_side=disable_calibration_arm,
        stop_side=lambda side:dict(contract='hhh.relay.stop',version=1,status='ready' if calibration_feedback['connected'] else 'unavailable',stopped=calibration_feedback['connected']))})
    real_measurement=owner._fresh_calibration_measurement
    def calibration_measurement(side,marker=None):
        if not calibration_feedback['connected']:raise ValueError('fresh camera and arm feedback required')
        measured_marker[0]=marker
        return real_measurement(side,marker)
    owner._fresh_calibration_measurement=calibration_measurement
    modules.update({'photon-board':board,'auto-pickup-game':owner,'dobot-mg400-relay':owner._hub_ctx.modules['dobot-mg400-relay']})
    game._progress.start()
    facade=load('mobile-ltz-api');facade.hub_init(FakeContext({'photon-game':game,'photon-progress':progress,'photon-level':level,'laser-tag-y':renderer, 'photon-board':board,
        'camera-calibration':SimpleNamespace(preview_snapshot=camera_descriptor,preview_frame=camera_frame),'auto-pickup-game':owner}))
    mcam1_state={'width':480,'height':320,'stale':False}
    mcam1_images={}
    def mcam1_frame():
        import cv2
        import numpy as np
        width,height=mcam1_state['width'],mcam1_state['height']
        if (width,height) not in mcam1_images:
            image=np.full((height,width,3),(75,105,35),dtype=np.uint8)
            cv2.rectangle(image,(10,10),(width-10,height-10),(135,210,240),4)
            cv2.putText(image,'MCAM1',(30,height//2),cv2.FONT_HERSHEY_SIMPLEX,1,(255,255,255),2)
            mcam1_images[width,height]=cv2.imencode('.jpg',image)[1].tobytes()
        return dict(contract='hhh.camera.still',version=1,status='ready',width=width,height=height,
                    captured_at=time.time()-(3 if mcam1_state['stale'] else 0),mime_type='image/jpeg',image=mcam1_images[width,height])
    @app.post('/__test/mcam1')
    def test_mcam1():
        data=request.get_json()
        mcam1_state.update(data)
        if data.get('enabled',True):facade._ctx.modules['mcam1']=SimpleNamespace(still_snapshot=mcam1_frame)
        else:facade._ctx.modules.pop('mcam1',None)
        return jsonify(ok=True)
    def tracking_snapshot():
        raw=observation()
        return dict(contract='photon.board.tracking',version=1,status=raw['status'],source='camera',
                    coordinate_space='corrected-camera-normalized',width=camera_state.get('width',1280),height=camera_state.get('height',720),
                    sampled_at=time.time(),frame_at=raw['frame_at'],limits={'stale_s':1.5},tags=[])
    board.tracking_snapshot=tracking_snapshot
    renderer.hub_init(FakeContext({'photon-game':game,'photon-level':level,'auto-pickup-game':owner,
                                 'photon-board':board}))
    app.register_blueprint(field.bp,url_prefix='/s/gamemaster/p/playfield-areas')
    app.register_blueprint(game.bp,url_prefix='/s/gamemaster/p/photon-game')
    app.register_blueprint(level.bp,url_prefix='/s/gamemaster/p/photon-level')
    app.register_blueprint(renderer.bp,url_prefix='/s/gamemaster/p/laser-tag-y')
    facade.delay_analysis.start(Path(folder)/'delay-analysis')
    facade.connection_log.LOG_PATH=Path(folder)/'connection-events.jsonl'
    app.register_blueprint(facade.bp,url_prefix='/s/gamemaster/p/mobile-ltz-api')
    app.register_blueprint(ui.bp,url_prefix='/s/green/p/mobile-ltz')
    app.register_blueprint(purple_ui.bp,url_prefix='/s/purple/p/mobile-ltz')
    app.register_blueprint(progress.bp,url_prefix='/s/gamemaster/p/photon-progress')
    for side in ('green','purple'):
        for slug in ('ltx','ltz-score'):
            path=ROOT/f'sandboxes/{side}/prototypes/{slug}/prototype.py'
            spec=importlib.util.spec_from_file_location('player_fixture_'+side+'_'+slug.replace('-','_'),path)
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            if slug=='ltx':
                module.hub_init(FakeContext({'cartesian-xyz-test':SimpleNamespace(),'auto-pickup-game':owner,'auto-pp-cal-2':SimpleNamespace()}))
                (ui if side=='green' else purple_ui)._ctx=FakeContext({'ltx':module})
            app.register_blueprint(module.bp,url_prefix=f'/s/{side}/p/{slug}')
    robot_targets={side:[0.,20.,30.,9.] for side in ('green','purple')};robot_commands=[]
    @app.route('/s/<side>/p/cartesian-xyz-test/api/<action>',methods=['GET','POST'])
    def fake_robot(side,action):
        if side not in robot_targets:abort(404)
        if action=='config':return jsonify(ok=True,identity={'is_player':True,'side':side},joint_limits={'j1':[-160,160],'j2':[-25,85],'j3':[-25,105],'j4':[-160,160]})
        data=request.get_json(silent=True) or {}
        if request.method=='POST':
            robot_commands.append({'side':side,'action':action,'data':data})
            if action=='connect':calibration_feedback['connected']=True;arm_enabled[side]=True
            if action=='enable':arm_enabled[side]=True
            if action=='joint-move':robot_targets[side]=[data[k] for k in ('j1','j2','j3','j4')]
        return jsonify(ok=True,connected=True,enabled=arm_enabled[side],feedback_ok=True,last_feedback=time.time(),
                       joints=[0.,20.,30.,9.],target=robot_targets[side],control_mode='joint',pose=[300.,100.,60.,9.],pump_mode='off')
    @app.get('/__test/robot-commands')
    def commands():return jsonify(robot_commands)
    @app.get('/__test/arm-enabled')
    def enabled_arms():return jsonify(arm_enabled)
    @app.get('/s/gamemaster/p/auto-pickup-game/api/<action>')
    def fake_pickup(action):
        if action=='calibration2':return jsonify(ok=True,calibration=owner._calibration2_public())
        if action=='state':return jsonify(ok=True,teams={},calibration={})
        return jsonify(ok=True,rows=[],scores=[],calibration={})
    @app.get('/s/gamemaster/p/webcam/api/tags')
    def fake_tags():return jsonify(tags=[],detections=[],corrected=True,width=1280,height=720)
    @app.get('/s/gamemaster/p/camera-calibration/api/corrected-stream')
    def fake_camera():return Response(camera_frame()['jpeg'],mimetype='image/jpeg')
    app.config['fixture_cleanup']=lambda: (facade.hub_stop(), progress.hub_stop())
    return app,game

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8117)
    parser.add_argument('--isolate-imports',action='store_true',help='Purge helper imports as the production hub does')
    parser.add_argument('--virtual-controls',action='store_true',help='Enable the test-only simulated arm command adapter')
    args=parser.parse_args();port=args.port
    with tempfile.TemporaryDirectory(prefix='mobile-ltz-') as folder:
        app,game=create_app(folder, virtual_controls=args.virtual_controls)
        if args.isolate_imports:
            for name,module in list(sys.modules.items()):
                if str(getattr(module,'__file__','') or '').startswith(str(ROOT/'sandboxes')+'/'):
                    del sys.modules[name]
        server=make_server('127.0.0.1',port,app,threaded=True)
        print(f'Mobile fixture http://127.0.0.1:{port}/s/green/p/mobile-ltz/',flush=True)
        try:server.serve_forever()
        finally:game.hub_stop();app.config['fixture_cleanup']()
