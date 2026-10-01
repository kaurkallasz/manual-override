"""Both mobile players, isolated from hardware and real saved profiles."""
import importlib.util
import copy
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from test_photon_framework import load, FakeContext, ROOT, Flask


def player_module(side, slug):
    path = ROOT / 'sandboxes' / side / 'prototypes' / slug / 'prototype.py'
    spec = importlib.util.spec_from_file_location('mobile_team_'+side+'_'+slug.replace('-', '_'), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MobileTeamTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.game, self.level = load('photon-game'), load('photon-level')
        self.game._settings = self.game.SettingsStore(Path(self.folder.name)/'settings.json')
        self.game.LOG_PATH = str(Path(self.folder.name)/'runs.jsonl')
        self.game._hub_ctx = FakeContext({'photon-level':self.level})
        self.game._sync_level()
        self.engine = self.game._engine
        self.engine.set_virtual_play(True)
        self.addCleanup(self.game.hub_stop)
        self.progress = SimpleNamespace(progress_snapshot=lambda identity: {
            'contract':'photon.progress', 'version':2, 'status':'ready',
            'player':{'name':identity['side'], 'unlocked_control':4, 'selected_control':4,'current_control_tier':4,'progression_stage':'playing'}})
        self.progress.public_snapshot=lambda side:self.progress.progress_snapshot({'side':side})
        self.engine.set_virtual_test_loadout(None,4)
        self.game._hub_ctx = FakeContext({'photon-level':self.level, 'photon-progress':self.progress})
        self.facade = load('mobile-ltz-api')
        self.facade.hub_init(FakeContext({'photon-game':self.game, 'photon-progress':self.progress}))
        self.app = Flask('mobile-team-tests')
        self.app.register_blueprint(self.facade.bp)
        self.client = self.app.test_client()

    def post(self, side, data, role=None):
        return self.client.post('/api/command?side='+side, json=data,
                                environ_overrides={'hhh.roles':{role or side}})

    def test_calibration_screen_precedes_motion_grant_and_never_leaks_partner_draft(self):
        cal={'contract':'hhh.cal2.session','version':1,'status':'ready','epoch':'live','sessions':{}}
        owner=SimpleNamespace(calibration_session_snapshot=lambda:copy.deepcopy(cal))
        self.facade.hub_init(FakeContext({'auto-pickup-game':owner}))
        for side,partner in (('green','purple'),('purple','green')):
            journey={'phase':'calibration','id':'selected','calibration_side':side,'active_side':None}
            with patch.object(self.facade,'_game',side_effect=lambda:(None,{'virtual_play':True,'journey':copy.deepcopy(journey)})):
                pending=self.facade.mobile_snapshot(side)
                self.assertEqual(pending['journey']['calibration_side'],side)
                self.assertIsNone(pending['mobile_calibration'])
                self.assertFalse(pending['mobile_calibration_ready'])
                session_id='selected:'+side
                cal.update(active_side=side,active_id=session_id,requires_activation=True)
                cal['sessions'][session_id]={'id':session_id,'side':side,'stage':'points','captures':{'30':{}},'epoch':'old','access_until':time.time()+30}
                restored=self.facade.mobile_snapshot(side)
                self.assertEqual(restored['mobile_calibration']['captures'],{'30':{}})
                self.assertFalse(restored['mobile_calibration_ready'])
                self.assertIsNone(self.facade.mobile_snapshot(partner)['mobile_calibration'])
                journey.update(active_side=side,session_id=session_id)
                cal.update(requires_activation=False)
                cal['sessions'][session_id]['epoch']='live'
                self.assertTrue(self.facade.mobile_snapshot(side)['mobile_calibration_ready'])
                for invalid in ({'motion_blocked':True},{'requires_activation':True}):
                    with patch.dict(cal,invalid):self.assertFalse(self.facade.mobile_snapshot(side)['mobile_calibration_ready'])
                for invalid in ({'paused':True},{'access_until':time.time()-1},{'epoch':'old'}):
                    with patch.dict(cal['sessions'][session_id],invalid):self.assertFalse(self.facade.mobile_snapshot(side)['mobile_calibration_ready'])
            cal['sessions'].clear()

    def test_malformed_calibration_owner_is_explicitly_unavailable(self):
        owner=SimpleNamespace(calibration_session_snapshot=lambda:{'contract':'hhh.cal2.session','version':True,'status':'ready'})
        self.facade.hub_init(FakeContext({'auto-pickup-game':owner}))
        with patch.object(self.facade,'_game',return_value=(None,{'virtual_play':True,'journey':{'phase':'calibration','calibration_side':'green'}})):
            value=self.facade.mobile_snapshot('green')
            self.assertFalse(value['mobile_calibration_ready'])
            self.assertIn('unavailable',value['mobile_calibration_error'])

    def test_marker_preparation_reaches_selected_phone_before_arm_activation(self):
        for side,partner in (('green','purple'),('purple','green')):
            preparation={'id':'prepare:'+side,'side':side,'ready':True,
                         'marker_positions':{str(i):{'camera':{'u':.2,'v':.3},'frame_at':time.time()} for i in range(30,36)}}
            owner=SimpleNamespace(calibration_session_snapshot=lambda:dict(contract='hhh.cal2.session',version=1,status='ready',
                active_side=side,active_id=preparation['id'],requires_activation=True,sessions={},marker_preparation=preparation))
            self.facade.hub_init(FakeContext({'auto-pickup-game':owner}))
            state={'virtual_play':False,'journey':{'phase':'calibration','id':'prepare','calibration_side':side,'active_side':None}}
            with patch.object(self.facade,'_game',side_effect=lambda:(None,copy.deepcopy(state))),patch.object(self.facade,'camera_view',side_effect=lambda game:dict(status='ready',tags=[])):
                phone=self.facade.mobile_snapshot(side)
                self.assertEqual(phone['mobile_calibration_preparation'],preparation)
                self.assertEqual(len(phone['mobile_camera']['tags']),6)
                self.assertIsNone(phone['mobile_calibration'])
                self.assertFalse(phone['mobile_calibration_ready'])
                self.assertTrue(phone['mobile_calibration_connect'])
                self.assertIsNone(self.facade.mobile_snapshot(partner)['mobile_calibration_preparation'])
                self.assertEqual(self.facade.mobile_snapshot(partner)['mobile_camera']['tags'],[])

    def test_cached_calibration_labels_remain_visible_only_for_the_selected_side(self):
        session={'id':'lesson:green','side':'green','stage':'points','epoch':'live','access_until':time.time()+30,
                 'marker_positions':{'30':{'camera':{'u':.2,'v':.3},'frame_at':time.time()-8}}}
        owner=SimpleNamespace(calibration_session_snapshot=lambda:dict(contract='hhh.cal2.session',version=1,status='ready',
                         active_side='green',active_id=session['id'],epoch='live',sessions={session['id']:session}))
        self.facade.hub_init(FakeContext({'auto-pickup-game':owner}))
        value={'virtual_play':False,'journey':{'phase':'calibration','id':'lesson','session_id':session['id'],'calibration_side':'green','active_side':'green'}}
        with patch.object(self.facade,'_game',side_effect=lambda:(None,copy.deepcopy(value))),patch.object(self.facade,'camera_view',side_effect=lambda game:dict(status='ready',tags=[])):
            self.assertEqual(self.facade.mobile_snapshot('green')['mobile_camera']['tags'],[dict(id=30,u=.2,v=.3,cached=True)])
            self.assertEqual(self.facade.mobile_snapshot('purple')['mobile_camera']['tags'],[])
        with patch.object(self.facade,'_game',side_effect=lambda:(None,copy.deepcopy(value))),patch.object(self.facade,'camera_view',return_value=dict(status='unavailable')):
            self.assertNotIn('tags',self.facade.mobile_snapshot('green')['mobile_camera'])

    def test_saved_calibrations_are_side_scoped_and_contract_checked(self):
        owner=SimpleNamespace(calibration_history=lambda side:dict(contract='hhh.cal2.history',version=1,status='ready',rows=[{'side':side}]))
        self.facade.hub_init(FakeContext({'auto-pickup-game':owner}))
        for side in ('green','purple'):
            response=self.client.get('/api/calibrations?side='+side,environ_overrides={'hhh.roles':{side}})
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.json['rows'],[{'side':side}])
            other='purple' if side=='green' else 'green'
            self.assertEqual(self.client.get('/api/calibrations?side='+other,environ_overrides={'hhh.roles':{side}}).status_code,403)
        owner.calibration_history=lambda side:dict(contract='hhh.cal2.history',version=True,status='ready')
        self.assertEqual(self.client.get('/api/calibrations?side=green',environ_overrides={'hhh.roles':{'green'}}).status_code,503)
        with patch.object(owner,'calibration_history',side_effect=RuntimeError('saved measurements unavailable')):
            response=self.client.get('/api/calibrations?side=green',environ_overrides={'hhh.roles':{'green'}})
            self.assertEqual(response.status_code,503)
            self.assertEqual(response.json['error'],'saved measurements unavailable')

    def test_ui_has_one_feature_source_but_independent_builds_and_discovery(self):
        modules = {side:player_module(side, 'mobile-ltz') for side in ('green', 'purple')}
        self.assertEqual(modules['green'].HERE, modules['purple'].HERE)
        self.assertEqual(modules['green'].HERE, ROOT/'shared/mobile_ltz')
        for side, ui in modules.items():
            descriptor = dict(contract=side+'.robot-controller', version=1, status='ready',
                              path='/s/'+side+'/p/ltx/?ltz=1&mobile=1&bridge=1')
            ui.hub_init(FakeContext({'ltx':SimpleNamespace(controller_contract=lambda:descriptor)}))
            app = Flask('ui-'+side);app.register_blueprint(ui.bp)
            with app.test_client() as client:
                html = client.get('/').text
                self.assertIn('data-mobile-team="'+side+'"', html)
                self.assertIn('mobile ltz · '+side.title(), html)
                self.assertIn('id="rotateView"', html)
                self.assertEqual(client.get('/api/physical-controller').json, descriptor)
                descriptor['contract'] = ('green' if side == 'purple' else 'purple')+'.robot-controller'
                self.assertEqual(client.get('/api/physical-controller').status_code, 503)
            self.addCleanup(ui.hub_stop)
        self.assertEqual(modules['green']._client['files'], modules['purple']._client['files'])
        self.assertNotEqual(modules['green'].client_contract()['build'], modules['purple'].client_contract()['build'])

    def test_each_ltx_discovers_its_local_dependencies_and_serves_the_same_bridge(self):
        for side in ('green', 'purple'):
            module = player_module(side, 'ltx')
            module.hub_init(FakeContext({slug:object() for slug in ('cartesian-xyz-test', 'auto-pickup-game', 'auto-pp-cal-2')}))
            descriptor = module.controller_contract()
            self.assertEqual(descriptor['contract'], side+'.robot-controller')
            self.assertEqual(descriptor['status'], 'ready')
            self.assertTrue(descriptor['path'].startswith('/s/'+side+'/'))
            app=Flask('ltx-'+side);app.register_blueprint(module.bp)
            with app.test_client() as client:
                self.assertEqual(module.MANIFEST['default_page'],'?ltz=1')
                page=client.get('/?ltz=1')
                try:self.assertIn('playerJointRig',page.text)
                finally:page.close()
                for name in ('joint-rig.js','live-game.js'):
                    library=client.get('/'+name)
                    try:
                        self.assertEqual(library.text,(ROOT/'shared/mobile_ltz'/name).read_text())
                        self.assertIn('no-store',library.headers['Cache-Control'])
                    finally:library.close()
                response=client.get('/mobile-bridge.js')
                try:self.assertEqual(response.text, (ROOT/'shared/mobile_ltz/arm-bridge.js').read_text())
                finally:response.close()
            module.hub_init(FakeContext({}));self.assertEqual(module.controller_contract()['status'], 'unavailable')
            module.hub_stop()

    def test_both_players_connect_their_relay_arm_before_acquiring_a_lease(self):
        for side in ('green', 'purple'):
            path=ROOT/'sandboxes'/side/'prototypes/cartesian-xyz-test/relay_client.py'
            spec=importlib.util.spec_from_file_location('mobile_relay_'+side,path)
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            relay=module.RelayClient('http://fake-relay',side)
            calls=[]
            def post(path,data):
                calls.append((path,data))
                return 200,{'ok':True,'token':'fake-token'}
            with patch.object(relay,'_get',return_value=(200,{'arms':{side:{'connected':False}}})), \
                 patch.object(relay,'_post',side_effect=post),patch.object(relay,'_start_heartbeat'):
                relay.connect()
            self.assertEqual(calls[:2],[('/api/connect',{'side':side}),
                                       ('/api/acquire',{'side':side,'mode':'cartesian'})])
            calls.clear()
            def failed(path,data):
                calls.append((path,data))
                return 503,{'ok':False,'error':'Robot unavailable'}
            with patch.object(relay,'_get',return_value=(200,{'arms':{}})), \
                 patch.object(relay,'_post',side_effect=failed),patch.object(relay,'_start_heartbeat'):
                with self.assertRaisesRegex(module.RelayError,'Robot unavailable'):relay.connect()
            self.assertEqual(calls,[('/api/connect',{'side':side})])

    def test_player_projection_and_authorization_cannot_cross_teams(self):
        for side in ('green', 'purple'):
            other = 'purple' if side == 'green' else 'green'
            response = self.client.get('/api/state?side='+side, environ_overrides={'hhh.roles':{side}})
            self.assertEqual(response.status_code, 200)
            state = response.json
            self.assertEqual(state['mobile_team'], side)
            self.assertEqual(state['mobile_arm']['side'], side)
            self.assertEqual(state['mobile_progress']['player']['name'], side)
            self.assertNotIn('mobile_arms', state)
            self.assertEqual({tag['id'] for tag in state['mobile_arm']['tags']}, {code for code, owner in self.engine.atom_owners.items() if owner == side})
            self.assertEqual(self.client.get('/api/state?side='+other, environ_overrides={'hhh.roles':{side}}).status_code, 403)
            self.assertEqual(self.post(side, {'action':'connect','side':other}).status_code, 403)
            self.assertEqual(self.post(side, {'action':'start'}).status_code, 400)
        self.assertEqual(self.client.get('/api/state?side=unknown', environ_overrides={'hhh.roles':{'gamemaster'}}).status_code, 400)

    def test_two_players_connect_move_and_stop_without_taking_the_other_session(self):
        sessions={}
        for side in ('green', 'purple'):
            result=self.post(side, {'action':'connect','client_id':('a' if side=='green' else 'b')*32,'request_id':'c'*32})
            self.assertEqual(result.status_code, 200, result.json)
            sessions[side]=result.json['arm']['session']
            self.assertEqual(result.json['arm']['side'], side)
        self.assertNotEqual(sessions['green'], sessions['purple'])
        for side, arm in self.engine.mobile_arms.items():
            self.assertTrue(arm.snapshot()['connected'])
            arm.select_control('joint')
            result=self.post(side, {'action':'joints','session':sessions[side],'sequence':1,'joints':[j+1 for j in arm.joints]})
            self.assertEqual(result.status_code,200,result.json)
        self.engine.step(.1)
        self.assertEqual(self.post('purple', {'action':'joints','session':sessions['green'],'sequence':2,'joints':[0,0,0]}).status_code,400)
        result=self.post('purple', {'action':'stop','session':sessions['purple']})
        self.assertEqual(result.status_code,200)
        self.assertFalse(self.engine.mobile_arms['purple'].snapshot()['connected'])
        self.assertTrue(self.engine.mobile_arm.snapshot()['connected'])

    def test_lifecycle_and_piece_changes_apply_to_both_arms(self):
        arms=dict(self.engine.mobile_arms)
        for arm in arms.values():arm.command({'action':'connect'},self.engine)
        self.engine.start()
        for side, arm in arms.items():
            self.assertIs(self.engine.mobile_arms[side],arm)
            self.assertTrue(arm.snapshot()['connected'])
        self.engine.pause()
        self.assertTrue(all(not arm.snapshot()['connected'] for arm in arms.values()))
        self.engine.reset()
        self.assertTrue(all(self.engine.mobile_arms[side] is not arms[side] for side in arms))
        settings={**self.engine.settings,'green_piece_1':201,'green_piece_2':202,'purple_piece_1':301,'purple_piece_2':302}
        self.engine.configure_piece_codes(settings)
        self.assertEqual(set(self.engine.mobile_arms['green'].tags),{201,202})
        self.assertEqual(set(self.engine.mobile_arms['purple'].tags),{301,302})
        self.engine.set_virtual_test_loadout(None,4)
        self.assertTrue(all(arm.unlocked_control==4 for arm in self.engine.mobile_arms.values()))

    def test_purple_geometry_is_opposite_and_pickup_placement_is_owned(self):
        green, purple=self.engine.mobile_arms.values()
        for joints in (green.joints,[green.joints[0]+1,*green.joints[1:]],[green.joints[0]-1,*green.joints[1:]]):
            g,p=green.pose(joints),purple.pose(joints)
            for joint in ('base','elbow','tip'):
                self.assertAlmostEqual(g[joint]['x']+p[joint]['x'],self.engine.level.width)
                self.assertAlmostEqual(g[joint]['y']+p[joint]['y'],self.engine.level.height)
            solved=purple.solve_xyz(p['tip']);again=purple.pose(solved)['tip']
            for axis in ('x','y','z'):self.assertAlmostEqual(again[axis],p['tip'][axis])
        purple.command({'action':'connect'},self.engine)
        purple.set_pump('suction',self.engine)
        self.assertEqual(purple.held,102)
        sid, socket=next((sid,s) for sid,s in self.engine.level.sockets.items() if s['owner']=='purple')
        with patch.object(purple,'pose',return_value={'tip':dict(x=socket['x'],y=socket['y'],z=40)}):purple.set_pump('blow',self.engine)
        self.assertEqual(self.engine.placements[sid]['owner'],'purple')
        with self.assertRaises(ValueError):purple.cue.validate_rows([{'piece':100,'destination':socket['aruco_id']}],purple,self.engine)

    def test_purple_turret_aim_accepts_only_its_own_tower(self):
        sid,socket=next((sid,s) for sid,s in self.engine.level.sockets.items() if s['owner']=='purple')
        self.engine.place(102,sid,source='virtual',team='purple');tower=self.engine.placements[sid]
        data=dict(action='turret_aim',side='purple',socket_id=sid,atom_tag_id=102,activation_started_at=tower['activation_started_at'],aim_instance=tower['aim_instance'],aim_revision=tower['aim_revision'],run_id=self.game._run_id,angle_degrees=45,spread=.25)
        self.assertEqual(self.post('purple',data).status_code,200)
        data.update(side='green',aim_revision=tower['aim_revision'])
        self.assertEqual(self.post('green',data).status_code,400)
        self.assertIsNone(self.engine.mobile_arms['purple'].token)

    def test_team_streams_do_not_share_player_progress_or_arm_state(self):
        self.assertIsNot(self.facade._team_live['green'],self.facade._team_live['purple'])
        responses=[]
        try:
            for side in ('green','purple'):
                response=self.client.get('/api/events?side='+side,environ_overrides={'hhh.roles':{side}},buffered=False)
                responses.append(response)
                packet=next(iter(response.response)).decode()
                self.assertIn('"mobile_team":"'+side+'"',packet)
                self.assertIn('"name":"'+side+'"',packet)
        finally:
            for response in responses:response.close()


if __name__=='__main__':unittest.main()
