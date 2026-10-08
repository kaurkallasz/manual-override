"""Co-op progression, calibration sequencing and GM tier matrix; no hardware."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid
from test_photon_framework import load, FakeContext, ROOT, Flask


def owner_file(slug,filename):
    path=ROOT/'sandboxes/gamemaster/prototypes'/slug/filename
    spec=importlib.util.spec_from_file_location('journey_fixture_'+filename.replace('.','_'),path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


class CalFixture:
    def __init__(self):
        self.state={'contract':'hhh.cal2.session','version':1,'status':'ready','active_side':None,'active_id':None,'sessions':{},'pending_stops':{},'epoch':'live'}
        self.order=[];self.stopped=True;self.after_release=None
    def calibration_session_snapshot(self):return copy.deepcopy(self.state)
    def calibration_session_maintain(self):
        if self.stopped:self.state['pending_stops']={}
        return self.calibration_session_snapshot()
    def calibration_session_begin(self,value):
        if self.state['pending_stops']:raise ValueError('previous stop is not confirmed')
        if self.state['active_side'] and self.state['active_id']!=value['id']:raise ValueError('occupied')
        self.order.append(value['side'])
        self.state.update(active_side=value['side'],active_id=value['id'],requires_activation=False)
        session=self.state['sessions'].setdefault(value['id'],{**value,'stage':'points','calibration_revision':2,'committed_at':time.time(),'arrivals':[]})
        session['access_until']=time.time()+30;session['epoch']=self.state['epoch']
        return self.calibration_session_snapshot()
    def calibration_session_finish(self,value):
        session=self.state['sessions'][value['id']]
        if len(session['arrivals'])!=2:raise ValueError('arrivals')
        session.update(stage='complete',evidence_id=value['evidence_id'])
        return self.calibration_session_snapshot()
    def calibration_session_complete(self,value):
        if value['side']!=self.state['active_side']:raise PermissionError('wrong side')
        session=self.state['sessions'][value['id']]
        session.update(stage='complete',evidence_id='measurements:'+value['id'],completion_basis='measured-targets')
        return self.calibration_session_snapshot()
    def calibration_session_release(self,value):
        if not self.stopped:
            if not value.get('defer_stop'):raise ValueError('motion has not stopped')
            self.state['pending_stops'][value['side']]=value['id']
        self.state.update(active_side=None,active_id=None)
        if self.after_release:
            callback=self.after_release;self.after_release=None;callback()
        return self.calibration_session_snapshot()
    def calibration_session_command(self,side,value):
        if side!=self.state['active_side']:raise PermissionError('wrong side')
        return self.calibration_session_snapshot()


class JourneyTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup);self.path=Path(self.folder.name)
        self.progress=load('photon-progress');self.progress.DATA_DIR=self.path/'progress';self.progress.hub_init(None);self.addCleanup(self.progress.hub_stop)
        for side in ('green','purple'):
            p=self.progress.player_command(side,{'action':'create','name':side,'operation_id':uuid.uuid4().hex})['result']['player_id']
            self.progress.player_command(side,{'action':'select','player_id':p})
        self.cal=CalFixture();self.modules={'photon-progress':self.progress,'auto-pickup-game':self.cal}
        self.Journey=owner_file('photon-game','journey.py').Journey
        self.journey=self.Journey(self.path/'journey.json',self.modules.get,lambda:None,lambda side:[100 if side=='green' else 102])
    def win(self):
        run_id=uuid.uuid4().hex
        self.progress.begin_attempt({'run_id':run_id,'reward_enabled':True,'metadata':{}})
        return self.progress.finalize_attempt({'run_id':run_id,'sequence':1,'kills':100,'outcome':'won','active_seconds':1500,'finished_at':time.time(),'released_orcs':100})['attempt']
    def gate(self):
        for _ in range(6):attempt=self.win()
        self.journey.result(attempt);self.journey.tick()
        return attempt
    def board(self,side):
        session=self.cal.state['sessions'][self.cal.state['active_id']]
        session.update(stage='tutorial',arrivals=[{},{}],pickup_evidence={'piece_id':100 if side=='green' else 102,'lifted_at':time.time()-2})
        return {'source':'camera','placement':{'relations':[{'relation_id':'placement:'+side,'arm':side,'marker_id':31,
                'movable_id':session['pickup_evidence']['piece_id'],'stable':True,'rank':0,'observed_since':time.time()-1}]}}
    def test_third_xyz_win_queues_green_first_without_waiting_thirty_seconds(self):
        a=self.gate();self.assertEqual(self.cal.order,['green']);self.assertGreater(self.journey.state['deadline'],time.time())
        self.assertEqual(set(a['calibration_milestones']),{p['id'] for p in self.progress.progress_snapshot()['roster'].values()})
        for p in self.progress.progress_snapshot()['roster'].values():
            self.assertEqual((p['current_control_tier'],p['progression_stage']),(3,'calibration_pending'))
        with self.assertRaises(PermissionError):self.journey.lesson_command('purple',{'action':'capture'})
    def test_both_complete_and_one_shared_upgrade_deadline(self):
        self.gate();deadline=self.journey.state['deadline']
        self.journey.finish('green',self.board('green'));self.assertEqual(self.cal.order,['green','purple'])
        self.assertEqual(self.journey.state['active_side'],'purple')
        self.journey.finish('purple',self.board('purple'))
        self.assertEqual(self.journey.state['deadline'],deadline)
        with patch('time.time',return_value=deadline+1):self.journey.tick()
        self.assertEqual(self.journey.state['phase'],'ready')
        self.journey.ready('green');self.journey.ready('purple');self.assertEqual(self.journey.start(),self.journey.state['id'])
        for p in self.progress.progress_snapshot()['roster'].values():self.assertTrue(p['lesson']['complete'])
    def test_target_completion_advances_both_players_without_board_placement(self):
        self.gate();deadline=self.journey.state['deadline']
        with self.assertRaises(PermissionError):self.journey.complete_calibration('purple')
        self.journey.complete_calibration('green')
        self.assertEqual(self.journey.state['active_side'],'purple')
        self.assertTrue(self.progress.progress_snapshot()['roster']['green']['lesson']['complete'])
        self.journey.complete_calibration('purple')
        self.assertEqual(self.journey.state['phase'],'upgrades');self.assertEqual(self.journey.state['deadline'],deadline)
        for p in self.progress.progress_snapshot()['roster'].values():
            self.assertTrue(p['lesson']['complete']);self.assertEqual(p['credits'],600)
        with patch('time.time',return_value=deadline+1):self.journey.tick()
        self.assertEqual(self.journey.state['phase'],'ready')
    def test_target_completion_advances_offline_but_keeps_motion_gate_until_stop_confirmation(self):
        self.gate();self.cal.stopped=False
        self.journey.complete_calibration('green')
        self.assertIsNone(self.journey.state['active_side']);self.assertEqual(self.journey.state['turn'],1)
        self.assertTrue(self.cal.state['pending_stops'])
        self.assertTrue(self.progress.progress_snapshot()['roster']['green']['lesson']['complete'])
        self.cal.stopped=True;self.journey.tick();self.journey.tick()
        self.assertEqual(self.journey.state['active_side'],'purple');self.assertEqual(self.journey.state['turn'],1)
        self.assertEqual(self.progress.progress_snapshot()['roster']['green']['credits'],600)
    def test_practice_can_start_from_ready_and_returns_to_lobby(self):
        attempt=self.win();self.journey.result(attempt)
        with patch('time.time',return_value=self.journey.state['deadline']+1):self.journey.tick()
        reservation=self.journey.start(False)
        a=self.progress.begin_attempt({'run_id':'practice-ready','reward_enabled':False,'metadata':{},'reservation_id':reservation})['attempt']
        self.journey.started(a['run_id'],False)
        self.assertEqual(self.journey.state['phase'],'playing')
        result=self.progress.finalize_attempt({'run_id':a['run_id'],'sequence':1,'kills':3,'outcome':'aborted','active_seconds':1,'finished_at':time.time(),'released_orcs':3})['attempt']
        self.journey.result(result)
        self.assertEqual(self.journey.state['phase'],'lobby')
        self.progress.player_command('green',{'action':'select','player_id':None})

    def test_practice_start_cannot_interrupt_calibration_or_its_failed_setup(self):
        self.journey.manual({'side':'both'})
        with self.assertRaisesRegex(ValueError,'calibration'):self.journey.start(False)
        self.journey.cancel()
        def failed(value):
            self.cal.state.update(active_side=value['side'],active_id=value['id'])
            raise ValueError('camera stale')
        with patch.object(self.cal,'calibration_session_begin',side_effect=failed):
            self.journey.manual({'side':'both'})
        self.assertIsNone(self.journey.state['active_side'])
        self.assertEqual(self.journey.snapshot()['calibration_side'],'green')
        with self.assertRaisesRegex(ValueError,'calibration'):self.journey.start(False)
        self.journey.cancel()
        self.assertIsNone(self.cal.state['active_side'])
        self.assertEqual(self.journey.state['phase'],'lobby')
        self.assertIsNone(self.journey.snapshot()['calibration_side'])

    def test_late_recovered_xyz_win_opens_green_calibration_once(self):
        for _ in range(5):self.win()
        self.progress.begin_attempt({'run_id':'late-win','reward_enabled':True,'metadata':{}})
        self.progress.recover_attempts()
        recovered=self.progress.attempt_snapshot('late-win')['attempt']
        self.journey.result(recovered)
        deadline=self.journey.state['deadline']
        result=self.progress.finalize_attempt({'run_id':'late-win','sequence':2,'kills':100,'outcome':'won',
               'active_seconds':1500,'finished_at':recovered['finished_at']+1,'released_orcs':100})['attempt']
        self.journey.result(result);self.journey.result(result);self.journey.tick()
        self.assertEqual(self.journey.state['deadline'],deadline)
        self.assertEqual(self.cal.order,['green'])
        self.assertEqual(self.journey.state['phase'],'calibration')

    def test_stop_failure_retains_green_and_never_grants_purple(self):
        self.gate();self.cal.stopped=False
        with self.assertRaisesRegex(ValueError,'stopped'):self.journey.finish('green',self.board('green'))
        self.assertEqual(self.journey.state['active_side'],'green');self.assertEqual(self.cal.order,['green'])
        self.cal.stopped=True;self.journey.tick();self.journey.tick();self.assertEqual(self.cal.order,['green','purple'])
    def test_restart_reacquires_same_draft_without_live_grant(self):
        self.gate();sid=self.journey.state['session_id'];self.cal.state.update(active_side=None,active_id=None,epoch='restart')
        fresh=self.Journey(self.journey.path,self.modules.get,lambda:None);fresh.tick()
        self.assertEqual(fresh.state['session_id'],sid);self.assertEqual(self.cal.state['sessions'][sid]['epoch'],'restart')
    def test_restart_with_a_restored_display_reservation_still_reactivates_draft(self):
        self.gate();sid=self.journey.state['session_id'];self.cal.state.update(epoch='restart',requires_activation=True)
        self.journey.tick()
        self.assertEqual(self.journey.state['session_id'],sid)
        self.assertEqual(self.cal.state['sessions'][sid]['epoch'],'restart')
        self.assertFalse(self.cal.state['requires_activation'])
    def test_gm_can_select_another_test_offline_but_activation_waits_for_stop(self):
        before=copy.deepcopy(self.progress.progress_snapshot()['roster'])
        self.journey.manual({'side':'green'});sid=self.journey.state['session_id']
        self.cal.stopped=False
        self.journey.manual({'side':'purple'})
        self.assertEqual(self.journey.state['queue'],['purple']);self.assertIsNone(self.journey.state['active_side'])
        self.assertEqual(self.journey.snapshot()['calibration_side'],'purple')
        self.assertEqual(self.cal.state['pending_stops'],{'green':sid})
        self.cal.stopped=True;self.journey.tick()
        self.assertEqual(self.cal.order,['green','purple']);self.assertEqual(self.journey.state['active_side'],'purple')
        self.journey.cancel();self.assertEqual(self.journey.state['phase'],'lobby')
        self.assertEqual(self.progress.progress_snapshot()['roster'],before)

    def test_opening_y_leaves_saved_practice_and_repeated_ticks_keep_game_screen(self):
        self.journey.manual({'side':'both'});self.cal.stopped=False
        fresh=self.Journey(self.journey.path,self.modules.get,lambda:None)
        fresh.show_game();fresh.tick();fresh.tick()
        self.assertEqual(fresh.state['phase'],'lobby')
        self.assertTrue(self.cal.state['pending_stops'])

    def test_show_game_pauses_earned_lesson_without_unlocking_or_auto_reopening_it(self):
        self.gate();old_id=self.journey.state['id'];roster=copy.deepcopy(self.progress.progress_snapshot()['roster'])
        self.journey.show_game();self.journey.tick();self.journey.tick()
        fresh=self.Journey(self.journey.path,self.modules.get,lambda:None);fresh.tick()
        self.assertEqual(fresh.state['phase'],'lobby')
        self.assertEqual(fresh.state['deferred_calibration']['id'],old_id)
        with self.assertRaisesRegex(ValueError,'calibration'):fresh.ready('green')
        self.assertEqual(self.progress.progress_snapshot()['roster'],roster)
        fresh.resume_calibration()
        self.assertEqual(fresh.state['id'],old_id);self.assertEqual(fresh.state['active_side'],'green')
    def test_gm_test_switch_cannot_skip_an_earned_calibration_turn(self):
        self.gate()
        with self.assertRaisesRegex(ValueError,'active calibration'):self.journey.manual({'side':'purple'})
        self.assertEqual(self.journey.state['active_side'],'green')
    def test_saved_rig_apply_preserves_the_earned_lesson_and_progress(self):
        self.gate();roster=copy.deepcopy(self.progress.progress_snapshot()['roster']);calls=[]
        def preview(value):
            calls.append('preview');return dict(contract='hhh.cal2.saved',version=1,status='ready')
        def apply(value):
            self.assertIsNone(self.cal.state['active_side'])
            calls.append('apply');return dict(contract='hhh.cal2.saved',version=1,status='ready',applied=True)
        self.cal.calibration_saved_preview=preview;self.cal.calibration_saved_apply=apply
        result=self.journey.apply_saved_calibration({'side':'green','id':'latest'})
        self.assertTrue(result['applied']);self.assertEqual(calls,['preview','apply'])
        self.assertEqual(self.journey.state['phase'],'lobby');self.assertTrue(self.journey.state['deferred_calibration'])
        self.assertEqual(self.progress.progress_snapshot()['roster'],roster)
        with self.assertRaisesRegex(ValueError,'calibration'):self.journey.ready('green')
    def test_lost_release_acknowledgement_replays_completed_receipt_once(self):
        self.gate();self.cal.after_release=lambda:(_ for _ in ()).throw(OSError('lost ack'))
        with self.assertRaises(OSError):self.journey.finish('green',self.board('green'))
        self.journey.tick();self.journey.tick();self.assertEqual(self.journey.state['active_side'],'purple')
        self.assertEqual(self.progress.progress_snapshot()['roster']['green']['credits'],600)
    def test_manual_calibration_all_scopes_preserves_players_and_returns_to_lobby(self):
        before=copy.deepcopy(self.progress.progress_snapshot()['roster'])
        for scope,order in [('green',['green']),('purple',['purple']),('both',['green','purple'])]:
            self.cal.order=[];self.journey.manual({'side':scope})
            for side in order:self.journey.finish(side,self.board(side))
            self.assertEqual(self.cal.order,order);self.assertEqual(self.journey.state['phase'],'lobby')
        self.assertEqual(self.progress.progress_snapshot()['roster'],before)
    def test_manual_calibration_without_profiles_still_works(self):
        self.modules.pop('photon-progress');self.journey.manual({'side':'both'})
        self.assertEqual(self.cal.order,['green']);self.assertEqual(self.journey.state['active_side'],'green')
    def test_ready_invalidated_by_purchase_or_profile_switch(self):
        self.journey.ready('green');self.journey.ready('purple')
        new=self.progress.player_command('green',{'action':'create','name':'new','operation_id':uuid.uuid4().hex})['result']['player_id']
        self.progress.player_command('green',{'action':'select','player_id':new})
        with self.assertRaisesRegex(ValueError,'current profiles'):self.journey.start()
    def test_expired_upgrade_locks_purchases_until_operator_cancel(self):
        a=self.win();self.journey.result(a)
        with patch('time.time',return_value=self.journey.state['deadline']+1):self.journey.tick()
        p=self.progress.progress_snapshot({'side':'green'})['player']
        with self.assertRaisesRegex(ValueError,'ready roster'):self.progress.player_command('green',{'action':'purchase','track':'damage-mortar','level':2,'revision':p['revision'],'operation_id':uuid.uuid4().hex})
        self.journey.cancel();self.progress.player_command('green',{'action':'select','player_id':p['id']})
    def test_calibration_fixes_both_identities_but_waiting_player_can_purchase(self):
        self.gate();p=self.progress.progress_snapshot()['roster']['purple']
        with self.assertRaisesRegex(ValueError,'calibration roster'):
            self.progress.player_command('purple',{'action':'select','player_id':None})
        self.progress.player_command('purple',{'action':'purchase','track':'damage-mortar','level':2,'revision':p['revision'],'operation_id':uuid.uuid4().hex})
        self.assertEqual(self.progress.progress_snapshot()['roster']['purple']['levels']['damage-mortar'],2)
        self.journey.finish('green',self.board('green'));self.journey.finish('purple',self.board('purple'))
        self.progress.player_command('purple',{'action':'select','player_id':None})
    def test_dependency_can_read_journey_while_operation_is_in_flight(self):
        original=self.progress.reserve_roster
        def callback(value):
            done=threading.Event();thread=threading.Thread(target=lambda:(self.journey.snapshot(),done.set()));thread.start()
            self.assertTrue(done.wait(1),'state lock held across owner call');thread.join();return original(value)
        self.journey.ready('green');self.journey.ready('purple')
        with patch.object(self.progress,'reserve_roster',side_effect=callback):self.journey.start()
    def test_result_retry_does_not_restart_deadline_or_duplicate_shared_score(self):
        a=self.win();self.journey.result(a);deadline=self.journey.state['deadline'];self.journey.result(a)
        self.assertEqual(deadline,self.journey.state['deadline'])
        history=self.progress.history_snapshot({'combined':True})['history']
        self.assertEqual((history['total'],history['rows'][0]['score']),(1,100))
        self.assertEqual([p['credits'] for p in self.progress.progress_snapshot()['roster'].values()],[100,100])
    def test_crashed_scored_game_recovers_to_shared_upgrades_without_deadlock(self):
        self.progress.begin_attempt({'run_id':'crashed','reward_enabled':True,'metadata':{}})
        self.journey.started('crashed')
        self.progress.recover_attempts()
        fresh=self.Journey(self.journey.path,self.modules.get,lambda:None)
        fresh.tick()
        self.assertEqual(fresh.state['phase'],'upgrades')
        self.assertEqual(fresh.state['processed'],['crashed'])
        self.assertTrue(all(p['wins']==0 for p in self.progress.progress_snapshot()['roster'].values()))


class CalibrationDraftTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.module=owner_file('auto-pickup-game','lesson.py');self.store=self.module.LessonStore(Path(self.folder.name)/'lesson.json')
        self.cal={'arms':{s:{'pickup_height':10,'points':{str(i):{'marker':i,'pose':{'set':True},'camera':{'u':.1,'v':.1}} for i in range(30,36)}} for s in ('green','purple')}}
        self.store.begin({'side':'green','id':'lesson','piece_ids':[100]},self.cal)
    def measurement(self,i=30,frame=None):return {'camera':{'u':.1+(i-30)*.1,'v':.2},'pose':[300+(i-30)*3,0,10,0],'frame_at':frame or time.time(),'feedback_at':time.time(),'camera_revision':'lens-one','rig_identity':{'ip':'fixture'},'pump':'suck'}
    def test_new_player_requires_six_fresh_captures_not_saved_model(self):
        self.assertEqual(self.store.snapshot()['sessions']['lesson']['captures'],{})
        for i in range(30,36):self.store.capture('green',{'id':'lesson','marker':i},self.measurement(i))
        self.assertEqual(self.store.snapshot()['sessions']['lesson']['stage'],'perspective')
        with self.assertRaises(ValueError):self.store.capture('green',{'id':'lesson','marker':30},self.measurement(frame=1))
    def test_heights_average_six_positions_and_recalculate_after_recapture(self):
        for marker,z in zip(range(30,36),(5,10,15,20,25,30)):
            measured=self.measurement(marker);measured['pose'][2]=z
            session=self.store.capture('green',{'id':'lesson','marker':marker},measured)['sessions']['lesson']
            if marker<35:self.assertIsNone(session['pickup_height'])
        self.assertEqual(session['pickup_height'],17.5)
        self.assertEqual(session['transport_height'],57.5)
        measured=self.measurement(30);measured['pose'][2]=65
        session=self.store.capture('green',{'id':'lesson','marker':30},measured)['sessions']['lesson']
        self.assertEqual(session['pickup_height'],27.5)
        self.assertEqual(session['draft']['transport_height'],67.5)
        # A pre-update unfinished draft resumes without separate Z captures.
        old=self.store.state['sessions']['lesson'];old.pop('pickup_height');old.pop('transport_height')
        self.module.atomic_json(self.store.path,self.store.state)
        fresh=self.module.LessonStore(self.store.path).snapshot()['sessions']['lesson']
        self.assertEqual((fresh['pickup_height'],fresh['transport_height']),(27.5,67.5))
    def test_frame_from_before_target_loading_cannot_be_a_capture(self):
        activation=self.store.snapshot()['sessions']['lesson']['activated_at']
        with self.assertRaisesRegex(ValueError,'targets loaded'):
            self.store.capture('green',{'id':'lesson','marker':30},self.measurement(frame=activation-.1))
        self.assertEqual(self.store.snapshot()['sessions']['lesson']['captures'],{})

    def test_write_failure_preserves_last_accepted_draft(self):
        before=self.store.snapshot()
        with patch.object(self.module,'atomic_json',side_effect=OSError('disk')):
            with self.assertRaises(OSError):self.store.capture('green',{'id':'lesson','marker':30},self.measurement())
        after=self.store.snapshot();self.assertEqual(after['sessions'],before['sessions']);self.assertEqual(after['revision'],before['revision'])
    def test_only_one_player_or_session_can_own_field(self):
        for side,sid in [('purple','other'),('green','other')]:
            with self.assertRaises(ValueError):self.store.begin({'side':side,'id':sid},self.cal)
    def test_camera_change_rejected_and_rig_calibration_never_cleared(self):
        self.store.capture('green',{'id':'lesson','marker':30},self.measurement())
        changed=self.measurement(31);changed['camera_revision']='changed'
        with self.assertRaisesRegex(ValueError,'camera'):self.store.capture('green',{'id':'lesson','marker':31},changed)
        self.assertTrue(self.cal['arms']['green']['points']['30']['pose']['set'])
    def test_expired_access_rejected_and_draft_survives_restart(self):
        self.store.capture('green',{'id':'lesson','marker':30},self.measurement())
        with patch('time.time',return_value=time.time()+31):
            with self.assertRaises(PermissionError):self.store.capture('green',{'id':'lesson','marker':31},self.measurement(31))
        fresh=self.module.LessonStore(self.store.path)
        self.assertIsNone(fresh.snapshot()['active_side']);self.assertEqual(len(fresh.snapshot()['sessions']['lesson']['captures']),1)
    def test_parallax_requires_ground_then_new_raised_frame_and_all_points(self):
        with self.assertRaises(ValueError):self.store.parallax('green',{'id':'lesson','marker':31,'action':'ground'},self.measurement())
        for i in range(30,36):self.store.capture('green',{'id':'lesson','marker':i},self.measurement(i))
        for i in (31,35,33,34):
            self.store.parallax('green',{'id':'lesson','marker':i,'action':'ground'},self.measurement(i,10))
            with self.assertRaises(ValueError):self.store.parallax('green',{'id':'lesson','marker':i,'action':'raised'},self.measurement(i,10))
            self.store.parallax('green',{'id':'lesson','marker':i,'action':'raised'},self.measurement(i,11))
        self.assertEqual(sum(bool(p) for p in self.store.snapshot()['sessions']['lesson']['draft']['parallax_points'].values()),4)

    def test_saved_calibration_is_immutable_and_survives_restart(self):
        self.store.capture('green',{'id':'lesson','marker':31},self.measurement(31))
        self.assertIn('31',self.store.snapshot()['sessions']['lesson']['ground'])
        self.store.mark_committed('green','lesson',7)
        archived=self.store.snapshot()['saved_calibrations']['lesson:7']
        self.store.capture('green',{'id':'lesson','marker':32},self.measurement(32))
        self.assertEqual(self.store.snapshot()['saved_calibrations']['lesson:7'],archived)
        fresh=self.module.LessonStore(self.store.path)
        self.assertEqual(fresh.snapshot()['saved_calibrations']['lesson:7'],archived)


class TestUnlockMatrix(unittest.TestCase):
    def test_gamemaster_all_four_levels_default_both_arms_and_never_changes_earned_state(self):
        with tempfile.TemporaryDirectory() as folder:
            game=load('photon-game');game._settings=game.SettingsStore(Path(folder)/'settings.json');game.LOG_PATH=str(Path(folder)/'runs.jsonl')
            game._hub_ctx=FakeContext({'photon-level':load('photon-level')});game._sync_level();game._engine.set_virtual_play(True)
            self.addCleanup(game.hub_stop)
            app=Flask('both-test-unlocks');app.register_blueprint(game.bp);client=app.test_client()
            for tier,mode in enumerate(('joint','xyz','targeting','cue'),1):
                response=client.post('/api/command',json={'action':'virtual_test_loadout','levels':None,'control':tier},environ_overrides={'hhh.roles':{'gamemaster'}})
                self.assertEqual(response.status_code,200,response.json)
                with patch.object(game._live,'stream',side_effect=lambda reader,**kwargs:reader()):
                    preview=game._orc_events()
                    self.assertEqual((preview['contract'],preview['version'],preview['virtual_test_control']),('photon.game.preview',1,tier))
                for side in ('green','purple'):
                    arm=game._engine.mobile_arms[side]
                    arm.command({'action':'stop'},game._engine,0)
                    arm.command({'action':'connect'},game._engine,0)
                    self.assertEqual((arm.unlocked_control,arm.control_mode),(tier,mode))
                    self.assertEqual(game.motion_policy(side)['tier'],tier)
                    for phase in ('ready','upgrades'):
                        with patch.object(game,'journey_snapshot',return_value={'phase':phase}):
                            policy=game.motion_policy(side)
                            self.assertEqual(policy['scope'],'practice')
                            self.assertFalse(policy['blocked'],(side,tier,phase))
                    with patch.object(game,'journey_snapshot',return_value={'phase':'calibration'}):
                        self.assertTrue(game.motion_policy(side)['blocked'])
                    with patch.object(game,'journey_snapshot',return_value={'phase':'lobby','motion_blocked':True,'motion_error':'stop unconfirmed'}):
                        self.assertTrue(game.motion_policy(side)['blocked'],'Returning to game does not bypass the physical stop gate')
                        self.assertEqual(game.motion_policy(side)['tier'],0)
                response=client.post('/api/command',json={'action':'virtual_test_loadout','levels':None,'control':tier},environ_overrides={'hhh.roles':{'green'}})
                self.assertEqual(response.status_code,403)
            game._engine.set_virtual_play(False)
            for tier in range(1,5):
                game.apply_command({'action':'virtual_test_loadout','levels':None,'control':tier})
                for side in ('green','purple'):self.assertEqual(game.motion_policy(side)['tier'],tier)
            game.apply_command({'action':'virtual_test_loadout','levels':None,'control':None})
            self.assertTrue(all(game.motion_policy(s)['scope']=='player' for s in ('green','purple')))


if __name__=='__main__':unittest.main()
