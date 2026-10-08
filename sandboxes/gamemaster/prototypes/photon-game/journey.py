"""Game-owned co-op sequencing. Cross-owner calls never hold the state lock."""
import copy
import json
import os
from pathlib import Path
import threading
import time
import uuid


class Journey:
    def __init__(self, path, module_reader, wake, piece_reader=lambda side: []):
        self.path, self.module_reader, self.wake = Path(path), module_reader, wake
        self.piece_reader=piece_reader
        self.lock = threading.RLock()
        self.operation_lock = threading.RLock()
        self.state = {'phase':'lobby','revision':0,'processed':[],'queue':[], 'turn':0,
                      'active_side':None,'practice':False,'error':None,'deadline':None,'ready':{}}
        try:
            saved = json.loads(self.path.read_text())
            if not isinstance(saved, dict) or saved.get('phase') not in ('lobby','playing','upgrades','ready','calibration'):
                raise ValueError('invalid game journey store')
            self.state.update(saved)
        except FileNotFoundError:
            pass

    def call(self, slug, function, contract, version, *args):
        module = self.module_reader(slug)
        if module is None or not callable(getattr(module,function,None)):
            raise ValueError(f'{slug} unavailable')
        value = getattr(module,function)(*args)
        if not isinstance(value,dict) or value.get('contract') != contract or type(value.get('version')) is not int or value['version'] != version or value.get('status') != 'ready':
            raise ValueError(f'{contract} v{version} unavailable')
        return value

    def _save(self, state):
        # Writers serialize operations; readers take only this short local lock.
        with self.lock:
            state = copy.deepcopy(state)
            state['revision'] = self.state['revision'] + 1
            self.path.parent.mkdir(parents=True,exist_ok=True)
            temp = self.path.with_name(self.path.name+'.'+uuid.uuid4().hex+'.tmp')
            try:
                with temp.open('w') as handle:
                    json.dump(state,handle,allow_nan=False)
                    handle.flush();os.fsync(handle.fileno())
                os.replace(temp,self.path)
                fd = os.open(self.path.parent,os.O_RDONLY)
                try: os.fsync(fd)
                finally: os.close(fd)
                self.state = state
            finally:
                temp.unlink(missing_ok=True)
        self.wake()

    def snapshot(self):
        with self.lock:
            state = copy.deepcopy(self.state)
            # The queued turn chooses the player's screen even before sensors
            # permit activation. It is presentation, never a motion grant.
            turn, queue = state.get('turn', 0), state.get('queue', [])
            state['calibration_side'] = (queue[turn] if state['phase']=='calibration'
                                         and 0 <= turn < len(queue) else None)
            return {'contract':'photon.game.journey','version':1,'status':'ready',
                    'server_time':time.time(), **state}

    def _state(self):
        with self.lock: return copy.deepcopy(self.state)

    def roster(self):
        return self.call('photon-progress','progress_snapshot','photon.progress',2)['roster']

    @staticmethod
    def identity(player):
        return {'id':player['id'],'revision':player['revision']} if player else None

    def result(self, attempt):
        with self.operation_lock:
            state = self._state()
            if not attempt.get('reward_enabled'):
                if state['phase']=='playing' and state.get('run_id')==attempt['run_id']:
                    state.update(phase='lobby',run_id=None,ready={},error=None)
                    self._save(state)
                return
            if attempt['run_id'] in state['processed']:
                # A late durable win may replace a synthetic restart result.
                # Re-open its required lesson once, without resetting the clock.
                if (attempt.get('interrupted_result') and attempt.get('calibration_milestones')
                        and state.get('id')==attempt['run_id'] and state['phase'] in ('upgrades','ready')):
                    self.call('photon-progress','release_roster','photon.progress',2,{'id':state['id']})
                    state.update(phase='calibration',queue=['green','purple'],turn=0,active_side=None,ready={},error=None)
                    self._save(state)
                return
            state['processed'].append(attempt['run_id'])
            state.update(phase='upgrades', deadline=time.time()+30, id=attempt['run_id'],
                         active_side=None, turn=0, queue=[], practice=False, error=None,ready={})
            if attempt.get('calibration_milestones'):
                state.update(phase='calibration',queue=['green','purple'])
            self._save(state)
        # The existing 250 ms owner worker activates Green after result delivery.

    def manual(self, value):
        side = value.get('side','both')
        if side not in ('green','purple','both'): raise ValueError('choose Green, Purple or both')
        with self.operation_lock:
            state = self._state()
            if state['phase']=='calibration':
                if not state.get('practice'):
                    raise ValueError('finish or abort the active calibration session first')
                # Offline arms may delay movement, but never trap the operator
                # in the old projection. The owner retains a durable stop gate.
                self.cancel(defer_stop=True)
                state = self._state()
            previous = copy.deepcopy(state)
            state.update(phase='calibration',practice=True,deadline=time.time()+30,
                         id='test:'+uuid.uuid4().hex,queue=['green','purple'] if side=='both' else [side],
                         turn=0,active_side=None,error=None,return_state=previous)
            self._save(state)
        self.tick()
        return self.snapshot()

    def _complete_turn(self, state, session):
        side = session['side']
        if not state['practice']:
            player = self.roster().get(side)
            if not player or player['id'] != session.get('player_id'):
                raise ValueError('calibrating player changed; operator recovery required')
            if player.get('progression_stage') == 'calibration_pending':
                self.call('photon-progress','complete_lesson','photon.progress',2,
                          {'player_id':player['id'],'operation_id':'lesson:'+session['id'],
                           'milestone_id':player['calibration_milestone'],'lesson_version':1,
                           'calibration_revision':session['calibration_revision'],'evidence_id':session['evidence_id']})
        self.call('auto-pickup-game','calibration_session_release','hhh.cal2.session',1,
                  {'side':side,'id':session['id'],'defer_stop':session.get('completion_basis')=='measured-targets'})
        state.update(active_side=None,turn=state['turn']+1,error=None)
        self._save(state)

    def tick(self):
        with self.operation_lock:
            state = self._state()
            try:
                owner = self.module_reader('auto-pickup-game')
                cal = (self.call('auto-pickup-game','calibration_session_maintain','hhh.cal2.session',1)
                       if owner else None)
                if state['phase']=='playing' and state.get('run_id'):
                    attempt=self.call('photon-progress','attempt_snapshot','photon.progress',2,state['run_id'])['attempt']
                    if attempt['outcome']!='running':
                        self.result(attempt)
                        state=self._state()
                if state['phase']=='lobby':
                    roster = self.roster()
                    if not state.get('deferred_calibration') and all(roster.get(s) for s in ('green','purple')) and any(p.get('progression_stage')=='calibration_pending' for p in roster.values()):
                        state.update(phase='calibration',id='resume:'+uuid.uuid4().hex,queue=['green','purple'],
                                     turn=0,active_side=None,deadline=time.time()+30,practice=False,ready={})
                        self._save(state)
                if state['phase']=='calibration':
                    if not state['practice']:
                        self.call('photon-progress','reserve_lesson_roster','photon.progress',2,{'id':state['id']})
                    if state['turn'] < len(state['queue']):
                        side = state['queue'][state['turn']]
                        session_id = state['id']+':'+side
                        if cal is None:
                            raise ValueError('calibration owner unavailable')
                        session = cal['sessions'].get(session_id)
                        # Receipt survives restart or a lost release acknowledgement.
                        if session and session.get('stage')=='complete':
                            self._complete_turn(state,session)
                        else:
                            if cal.get('active_side') and cal.get('active_id') != session_id:
                                raise ValueError('another calibration owns the playfield')
                            if not session or cal.get('requires_activation') or cal.get('active_id') != session_id or cal.get('active_side') != side:
                                player = None if state['practice'] else self.roster().get(side)
                                if not state['practice'] and not player: raise ValueError('both players must remain selected during calibration')
                                self.call('auto-pickup-game','calibration_session_begin','hhh.cal2.session',1,
                                          {'id':session_id,'side':side,'player_id':player['id'] if player else None,'practice':state['practice'],'piece_ids':self.piece_reader(side)})
                            if state.get('active_side') != side or state.get('session_id') != session_id:
                                state.update(active_side=side,session_id=session_id,error=None)
                                self._save(state)
                    else:
                        if not state['practice']:
                            self.call('photon-progress','release_roster','photon.progress',2,{'id':state['id']})
                        if state.get('return_state'):
                            restored = state['return_state']
                            restored['processed']=state['processed']
                            state=restored
                        else:
                            state.update(phase='upgrades',active_side=None)
                        self._save(state)
                if state['phase']=='upgrades' and time.time()>=state['deadline']:
                    self.call('photon-progress','reserve_roster','photon.progress',2,{'id':state['id']})
                    state.update(phase='ready',error=None)
                    self._save(state)
                if state.get('error'):
                    state['error']=None;self._save(state)
            except Exception as exc:
                if state.get('error')!=str(exc):
                    state['error']=str(exc);self._save(state)

    def lesson_command(self, side, value):
        with self.operation_lock:
            state=self._state()
            if state['phase']!='calibration' or state['active_side']!=side:
                raise PermissionError('wait for your calibration turn')
            return self.call('auto-pickup-game','calibration_session_command','hhh.cal2.session',1,
                             side,{**value,'id':state['session_id']})

    def finish(self, side, board):
        with self.operation_lock:
            state=self._state()
            if state['active_side']!=side: raise PermissionError('wait for your calibration turn')
            cal=self.call('auto-pickup-game','calibration_session_snapshot','hhh.cal2.session',1)
            session=cal['sessions'][state['session_id']]
            if session['stage']!='complete':
                relation=next((r for r in board.get('placement',{}).get('relations',[]) if r.get('arm')==side and r.get('stable') and r.get('rank')==0
                               and r.get('marker_id') in range(30,36) and r.get('movable_id')==(session.get('pickup_evidence') or {}).get('piece_id') and r.get('observed_since',0)>(session.get('pickup_evidence') or {}).get('lifted_at',time.time())),None)
                if not relation or (board.get('source')=='simulation' and not state['practice']):
                    raise ValueError('complete the guided pickup and stable placement first')
                cal=self.call('auto-pickup-game','calibration_session_finish','hhh.cal2.session',1,
                              {'side':side,'id':session['id'],'evidence_id':relation['relation_id']})
                session=cal['sessions'][session['id']]
            self._complete_turn(state,session)
        self.tick()
        return self.snapshot()

    def complete_calibration(self, side):
        with self.operation_lock:
            state=self._state()
            selected=state['queue'][state['turn']] if state['turn']<len(state['queue']) else None
            if state['phase']!='calibration' or selected!=side:
                raise PermissionError('wait for your calibration turn')
            session_id=state['id']+':'+side
            cal=self.call('auto-pickup-game','calibration_session_complete','hhh.cal2.session',1,
                          {'side':side,'id':session_id})
            session=cal.get('sessions',{}).get(session_id,{})
            if session.get('stage')!='complete' or session.get('side')!=side:
                raise ValueError('Calibration completion receipt unavailable')
            self._complete_turn(state,session)
        self.tick()
        return self.snapshot()

    def start(self, reward_enabled=True):
        with self.operation_lock:
            state=self._state()
            if state['phase'] not in ('lobby','ready','playing'): raise ValueError('finish the shared upgrades/calibration phase before Start')
            if state.get('error'): raise ValueError(state['error'])
            if not reward_enabled:
                # Practice can use an already frozen roster without requiring
                # earned-game Ready confirmations or leaking its reservation.
                return state.get('id') if state['phase']=='ready' else None
            roster=self.roster()
            if not all(state['ready'].get(s)==self.identity(roster.get(s)) and roster.get(s) for s in ('green','purple')):
                raise ValueError('both players must confirm Ready for their current profiles before scored Start')
            reservation=state.get('id') if state['phase']=='ready' else 'ready:'+uuid.uuid4().hex
            self.call('photon-progress','reserve_roster','photon.progress',2,{'id':reservation,'expected_players':{s:self.identity(p) for s,p in roster.items()}})
            if state['phase']!='ready':
                state.update(phase='ready',id=reservation,practice=False);self._save(state)
            return reservation

    def ready(self,side):
        with self.operation_lock:
            state=self._state()
            if state['phase'] not in ('lobby','ready'): raise ValueError('finish upgrades and calibration first')
            player=self.roster().get(side)
            if not player or player.get('progression_stage')!='playing': raise ValueError('select a player and complete calibration first')
            state['ready'][side]=self.identity(player)
            self._save(state)
            return self.snapshot()

    def cancel(self, defer_stop=False):
        with self.operation_lock:
            state=self._state()
            deferred = (copy.deepcopy(state) if defer_stop and state['phase']=='calibration' and not state.get('practice') else None)
            if state['phase']=='calibration':
                cal=self.call('auto-pickup-game','calibration_session_snapshot','hhh.cal2.session',1)
                side=state.get('active_side') or (state['queue'][state['turn']] if state['turn']<len(state['queue']) else None)
                session_id=state.get('id','')+':'+str(side)
                if cal.get('active_id')==session_id and cal.get('active_side')==side:
                    self.call('auto-pickup-game','calibration_session_release','hhh.cal2.session',1,
                              {'side':side,'id':session_id,'defer_stop':defer_stop})
                elif cal.get('active_side'):
                    raise ValueError('another calibration owns the playfield')
            if not state.get('practice') and state.get('id'):
                self.call('photon-progress','release_roster','photon.progress',2,{'id':state['id']})
            state=state.get('return_state') or {**state,'phase':'lobby','queue':[],'turn':0,'active_side':None,'ready':{},'deadline':None,'error':None}
            if deferred:
                state['deferred_calibration'] = deferred
            self._save(state)
        return self.snapshot()

    def show_game(self):
        with self.operation_lock:
            if self._state()['phase']=='calibration':
                return self.cancel(defer_stop=True)
            return self.snapshot()

    def apply_saved_calibration(self,value):
        with self.operation_lock:
            # Resolve/validate the selection before changing the current screen.
            self.call('auto-pickup-game','calibration_saved_preview','hhh.cal2.saved',1,value)
            self.show_game()
            return self.call('auto-pickup-game','calibration_saved_apply','hhh.cal2.saved',1,value)

    def resume_calibration(self):
        with self.operation_lock:
            state = self._state()
            deferred = state.get('deferred_calibration')
            if state['phase']!='lobby' or not deferred:
                raise ValueError('no paused progression calibration to resume')
            deferred.update(active_side=None,error=None,processed=state['processed'])
            self._save(deferred)
        self.tick()
        return self.snapshot()

    def started(self, run_id, reward_enabled=True):
        with self.operation_lock:
            state=self._state();state.update(phase='playing',run_id=run_id,practice=not reward_enabled,deadline=None,error=None,ready={})
            self._save(state)
