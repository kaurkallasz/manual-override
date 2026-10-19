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
                      'active_side':None,'calibration_setup':False,'error':None,'deadline':None,'ready':{}}
        try:
            saved = json.loads(self.path.read_text())
            if not isinstance(saved, dict) or saved.get('phase') not in ('lobby','playing','results','ready','calibration'):
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
            for key in ('paused_game_calibrations','reset_stop_error','reset_stop_sides'):
                state.setdefault(key,copy.deepcopy(self.state.get(key,{} if key=='paused_game_calibrations' else None)))
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
            state.pop('paused_game_calibrations',None)
            # The queued turn chooses the player's screen even before sensors
            # permit activation. It is presentation, never a motion grant.
            turn, queue = state.get('turn', 0), state.get('queue', [])
            state['calibration_side'] = (queue[turn] if state['phase']=='calibration'
                                         and 0 <= turn < len(queue) else None)
            return {'contract':'photon.game.journey','version':1,'status':'ready',
                    'server_time':time.time(), **state}

    def _state(self):
        with self.lock: return copy.deepcopy(self.state)

    @staticmethod
    def _flow(state):
        return {k:copy.deepcopy(v) for k,v in state.items()
                if k not in ('paused_game_calibrations','reset_stop_error','reset_stop_sides')}

    def checkpoint_calibration(self, roster):
        """Keep sequencing with Game; the calibration owner keeps measured samples."""
        with self.operation_lock:
            state=self._state()
            current=state if state['phase']=='calibration' else state.get('deferred_calibration')
            game=(roster.get('saved_games') or {}).get('active')
            if not current or not game:return
            checkpoint={'event_id':roster['events']['active_id'],
                        'players':{s:p['id'] for s,p in roster['roster'].items()},
                        'milestones':{s:p.get('calibration_milestone') for s,p in roster['roster'].items()},
                        'journey':{k:copy.deepcopy(current[k]) for k in
                                   ('phase','id','queue','turn','calibration_setup','run_id') if k in current}}
            state.setdefault('paused_game_calibrations',{})[game['id']]=checkpoint
            self._save(state)

    def restore_game_calibration(self, roster):
        with self.operation_lock:
            state=self._state()
            game=(roster.get('saved_games') or {}).get('active')
            checkpoint=state.get('paused_game_calibrations',{}).get(game['id']) if game else None
            if not checkpoint:return False
            if (checkpoint['event_id']!=roster['events']['active_id']
                    or checkpoint['players']!={s:p['id'] for s,p in roster['roster'].items()}
                    or checkpoint['milestones']!={s:p.get('calibration_milestone') for s,p in roster['roster'].items()}):
                raise ValueError('Saved calibration participants changed')
            state.update(checkpoint['journey'])
            state.update(active_side=None,ready={},auto_start=None,deadline=None,error=None)
            state['paused_game_calibrations'].pop(game['id'])
            self._save(state)
        self.tick()
        return True

    def reset_stop(self, error, sides=None):
        with self.operation_lock:
            state=self._state()
            if sides is not None and (not isinstance(sides,list) or any(s not in ('green','purple') for s in sides)):
                raise ValueError('valid reset stop sides required')
            pending=[] if error is None else sorted(set(sides)) if sides is not None else state.get('reset_stop_sides')
            if state.get('reset_stop_error')!=error or state.get('reset_stop_sides')!=pending:
                state['reset_stop_error']=error
                state['reset_stop_sides']=pending
                self._save(state)

    def roster(self):
        return self.call('photon-progress','progress_snapshot','photon.progress',2)['roster']

    @staticmethod
    def _pending_turn(roster, queue):
        return next((i for i,side in enumerate(queue)
                     if roster.get(side,{}).get('progression_stage')=='calibration_pending'),len(queue))

    @staticmethod
    def _recorded_calibration_id(roster, cal):
        """Recover old saves through a verified completion receipt, never recency."""
        candidates=set()
        for side,player in roster.items():
            lesson=player.get('lesson') or {}
            receipt=lesson.get('receipt') or {}
            operation=receipt.get('operation_id','')
            suffix=':'+side
            if (not lesson.get('complete') or not operation.startswith('lesson:')
                    or not operation.endswith(suffix) or receipt.get('player_id')!=player['id']
                    or receipt.get('milestone_id')!=player.get('calibration_milestone')):
                continue
            session_id=operation[len('lesson:'):]
            session=cal.get('sessions',{}).get(session_id,{})
            if (session.get('player_id')!=player['id'] or session.get('side')!=side
                    or session.get('purpose','progression')!='progression' or session.get('stage')!='complete'
                    or session.get('calibration_revision')!=receipt.get('calibration_revision')
                    or session.get('evidence_id')!=receipt.get('evidence_id')):
                continue
            milestone=player['calibration_milestone'].removesuffix(':'+player['id'])
            if not all(p.get('calibration_milestone')==milestone+':'+p['id'] for p in roster.values()):
                continue
            root=session_id[:-len(suffix)]
            pending=[(s,p) for s,p in roster.items() if p.get('progression_stage')=='calibration_pending']
            if pending and all((draft:=cal.get('sessions',{}).get(root+':'+s,{})).get('player_id')==p['id']
                               and draft.get('side')==s and draft.get('purpose','progression')=='progression'
                               for s,p in pending):
                candidates.add(root)
        return next(iter(candidates)) if len(candidates)==1 else None

    def _reconcile_calibration(self, state, roster, cal):
        """Loaded completion records choose the turn even while hardware is offline."""
        turn=state['turn']
        while turn<len(state['queue']) and roster.get(state['queue'][turn],{}).get('progression_stage')=='playing':
            turn+=1
        root=self._recorded_calibration_id(roster,cal)
        # A new draft with measurements wins over an older receipt's sibling.
        current=[cal.get('sessions',{}).get(state['id']+':'+s,{}) for s in state['queue'][turn:]]
        if not root or any(s.get('captures') for s in current):root=state['id']
        if turn==state['turn'] and root==state['id']:return
        active_id=cal.get('active_id')
        if cal.get('active_side') and active_id==state['id']+':'+cal['active_side']:
            self.call('auto-pickup-game','calibration_session_release','hhh.cal2.session',1,
                      {'side':cal['active_side'],'id':active_id,'defer_stop':True})
        if root!=state['id']:
            self.call('photon-progress','release_roster','photon.progress',2,{'id':state['id']})
        state.update(id=root,turn=turn,active_side=None,session_id=None,error=None)
        self._save(state)

    @staticmethod
    def identity(player):
        return {'id':player['id'],'revision':player['revision']} if player else None

    def result(self, attempt):
        with self.operation_lock:
            state=self._state()
            if attempt['run_id'] in state['processed']:
                return
            state['processed'].append(attempt['run_id'])
            state.update(phase='results',id=attempt['run_id'],run_id=attempt['run_id'],deadline=None,
                         game_complete=attempt['outcome']=='won' and attempt['metadata'].get('contract_control_tier')==4,
                         active_side=None,turn=0,queue=[],calibration_setup=False,error=None,ready={},auto_start=None)
            self._save(state)

    def prepare_next(self):
        with self.operation_lock:
            state=self._state()
            if state['phase'] not in ('results','ready','lobby'):raise ValueError('Finish the match or calibration first')
            roster=self.roster()
            if len(roster)!=2:raise ValueError('Select both event players')
            state.update(active_side=None,error=None,ready={},calibration_setup=False,auto_start=None)
            if any(p['progression_stage']=='calibration_pending' for p in roster.values()):
                state.update(phase='calibration',queue=['green','purple'],turn=self._pending_turn(roster,['green','purple']),
                             id=state.get('id') or 'calibration:'+uuid.uuid4().hex)
            else:state.update(phase='ready')
            self._save(state)
        self.tick()
        return self.snapshot()

    def manual(self, value):
        side = value.get('side','both')
        if side not in ('green','purple','both'): raise ValueError('choose Green, Purple or both')
        with self.operation_lock:
            state = self._state()
            if state['phase']=='calibration':
                if not state.get('calibration_setup'):
                    raise ValueError('finish or abort the active calibration session first')
                # Offline arms may delay movement, but never trap the operator
                # in the old projection. The owner retains a durable stop gate.
                self.cancel(defer_stop=True)
                state = self._state()
            previous = self._flow(state)
            previous['auto_start']=None
            state.update(phase='calibration',calibration_setup=True,deadline=time.time()+30,
                         id='setup:'+uuid.uuid4().hex,queue=['green','purple'] if side=='both' else [side],
                         turn=0,active_side=None,error=None,return_state=previous,auto_start=None)
            self._save(state)
        self.tick()
        return self.snapshot()

    def _complete_turn(self, state, session):
        side = session['side']
        if not state['calibration_setup']:
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
                if state['phase']=='lobby':
                    roster = self.roster()
                    if not state.get('deferred_calibration') and all(roster.get(s) for s in ('green','purple')) and any(p.get('progression_stage')=='calibration_pending' for p in roster.values()):
                        state.update(phase='calibration',id='resume:'+uuid.uuid4().hex,queue=['green','purple'],
                                     turn=self._pending_turn(roster,['green','purple']),active_side=None,
                                     deadline=time.time()+30,calibration_setup=False,ready={})
                        self._save(state)
                if state['phase']=='calibration' and not state['calibration_setup']:
                    cal=self.call('auto-pickup-game','calibration_session_snapshot','hhh.cal2.session',1) if owner else {}
                    self._reconcile_calibration(state,self.roster(),cal)
                cal = (self.call('auto-pickup-game','calibration_session_maintain','hhh.cal2.session',1)
                       if owner else None)
                if state['phase']=='playing' and state.get('run_id'):
                    attempt=self.call('photon-progress','attempt_snapshot','photon.progress',2,state['run_id'])['attempt']
                    if attempt['outcome']!='running':
                        self.result(attempt)
                        state=self._state()
                if state['phase']=='calibration':
                    if not state['calibration_setup']:
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
                                player = None if state['calibration_setup'] else self.roster().get(side)
                                if not state['calibration_setup'] and not player: raise ValueError('both players must remain selected during calibration')
                                self.call('auto-pickup-game','calibration_session_begin','hhh.cal2.session',1,
                                          {'id':session_id,'side':side,'player_id':player['id'] if player else None,'purpose':'setup' if state['calibration_setup'] else 'progression','piece_ids':self.piece_reader(side)})
                            if state.get('active_side') != side or state.get('session_id') != session_id:
                                state.update(active_side=side,session_id=session_id,error=None)
                                self._save(state)
                    else:
                        if not state['calibration_setup']:
                            self.call('photon-progress','release_roster','photon.progress',2,{'id':state['id']})
                        if state.get('return_state'):
                            restored = state['return_state']
                            restored['processed']=state['processed']
                            state=restored
                        else:
                            state.update(phase='ready',active_side=None)
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
                if not relation or (board.get('source')=='simulation' and not state['calibration_setup']):
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
            if state['phase'] not in ('lobby','results','ready','playing'): raise ValueError('finish or cancel calibration before Start')
            if state.get('error'): raise ValueError(state['error'])
            roster=self.roster()
            # The operator decides when to start. Ready acknowledgements are
            # advisory; reserve the current profiles atomically with Progress.
            reservation=state.get('id') or 'ready:'+uuid.uuid4().hex
            self.call('photon-progress','reserve_roster','photon.progress',2,{'id':reservation,'expected_players':{s:self.identity(p) for s,p in roster.items()}})
            try:
                if state['phase']!='ready':
                    state.update(phase='ready',id=reservation,calibration_setup=False);self._save(state)
            except Exception:
                self.call('photon-progress','release_start_reservation','photon.progress',2,{'id':reservation})
                raise
            return reservation

    def release_start(self, reservation=None):
        with self.operation_lock:
            state=self._state()
            if state['phase'] not in ('lobby','ready','results'):return
            reservation=reservation or state.get('id')
            if reservation:
                self.call('photon-progress','release_start_reservation','photon.progress',2,{'id':reservation})

    @staticmethod
    def readiness(state, teams):
        pair={side:p['id'] for side,p in teams.items()}
        players={}
        for side in ('green','purple'):
            p=teams.get(side);ack=state.get('ready',{}).get(side) or {}
            pending=bool(p and p.get('progression_stage')=='calibration_pending')
            ready=bool(p and (not pending or state.get('phase')=='results') and ack.get('id')==p['id']
                       and ack.get('pair',pair)==pair
                       and ack.get('tier',p['tier'])==p['tier']
                       and ack.get('levels',p['levels'])==p['levels'])
            players[side]={'id':p['id'] if p else None,'name':p['name'] if p else None,
                           'ready':ready,'state':'unselected' if not p else 'ready' if ready else 'calibration' if pending else 'waiting'}
        choices={ack.get('choice','continue') for ack in state.get('ready',{}).values()}
        return {'status':'ready','players':players,'all_ready':len(choices)==1 and all(p['ready'] for p in players.values())}

    def ready(self,side,choice="continue"):
        with self.operation_lock:
            state=self._state()
            if state['phase'] not in ('lobby','results','ready'): raise ValueError('finish calibration first')
            roster=self.roster();player=roster.get(side)
            if not player:raise ValueError('Select an event player')
            if state['phase']!='results' and any(p.get('progression_stage')=='calibration_pending' for p in roster.values()):return self.prepare_next()
            state['ready'][side]={**self.identity(player),'choice':choice,'pair':{s:p['id'] for s,p in roster.items()},
                                  'tier':player['selected_control'],'levels':copy.deepcopy(player['levels'])}
            self._save(state)
            return self.snapshot()

    def replay_result(self, run_id):
        with self.operation_lock:
            state=self._state()
            state.update(phase='results',id=run_id,run_id=run_id,game_complete=False,ready={},auto_start=None)
            self._save(state)
        return self.prepare_next()

    def queue_start(self, context):
        """Retain both players' consent while required calibration completes."""
        with self.operation_lock:
            state=self._state()
            if state['phase'] not in ('ready','calibration') or state.get('run_id')!=context['run_id']:
                raise ValueError('Level transition changed; refresh before continuing')
            state['auto_start']=copy.deepcopy(context)
            self._save(state)

    def start_failed(self, error):
        with self.operation_lock:
            state=self._state()
            if state.get('auto_start'):
                state['auto_start']['error']=str(error)
                self._save(state)

    def cancel(self, defer_stop=False):
        with self.operation_lock:
            state=self._state()
            deferred = (self._flow(state) if defer_stop and state['phase']=='calibration' and not state.get('calibration_setup') else None)
            if state['phase']=='calibration':
                cal=self.call('auto-pickup-game','calibration_session_snapshot','hhh.cal2.session',1)
                side=state.get('active_side') or (state['queue'][state['turn']] if state['turn']<len(state['queue']) else None)
                session_id=state.get('id','')+':'+str(side)
                if cal.get('active_id')==session_id and cal.get('active_side')==side:
                    self.call('auto-pickup-game','calibration_session_release','hhh.cal2.session',1,
                              {'side':side,'id':session_id,'defer_stop':defer_stop})
                elif cal.get('active_side'):
                    raise ValueError('another calibration owns the playfield')
            if not state.get('calibration_setup') and state.get('id'):
                self.call('photon-progress','release_roster','photon.progress',2,{'id':state['id']})
            state=state.get('return_state') or {**state,'phase':'lobby','queue':[],'turn':0,'active_side':None,'ready':{},'deadline':None,'error':None,'result_pending':False}
            state['auto_start']=None
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

    def reset_lobby(self, reset_operation=None):
        """A loaded/new pair must not inherit another game's lesson or next-level receipt."""
        with self.operation_lock:
            state = self._state()
            self._save({'phase':'lobby', 'processed':state['processed'], 'queue':[], 'turn':0,
                        'active_side':None, 'calibration_setup':False, 'error':None, 'deadline':None, 'ready':{},
                        'reset_operation':reset_operation or state.get('reset_operation')})
        return self.snapshot()

    def started(self, run_id, reward_enabled=True):
        with self.operation_lock:
            state=self._state();state.update(phase='playing',run_id=run_id,calibration_setup=False,deadline=None,error=None,ready={},
                                            continued_from=(state.get('auto_start') or {}).get('run_id'),auto_start=None)
            self._save(state)
