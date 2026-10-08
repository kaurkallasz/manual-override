"""Cal 2's durable drafts and single playfield reservation; no device ownership."""
import copy
import itertools
import json
import math
import os
from pathlib import Path
import threading
import time
import uuid


def _spread(points):
    """Require anchors spanning the board, not one edge or one occluding object."""
    return any(abs((b['u']-a['u'])*(c['v']-a['v'])-(b['v']-a['v'])*(c['u']-a['u'])) >= .02
               for a,b,c in itertools.combinations(points,3))


def _pixel_distance(a, b, size):
    return math.hypot((a['u']-b['u'])*size[0], (a['v']-b['v'])*size[1])


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temp.open('w') as handle:
            json.dump(value, handle, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        temp.unlink(missing_ok=True)


def set_capture_heights(session):
    """Each arm uses its six measured ground Z values, plus 40 mm clearance."""
    draft = session['draft']
    points = list(draft['points'].values())
    complete = (set(session['captures']) == {str(i) for i in range(30, 36)}
                and len(points) == 6 and {p['marker'] for p in points} == set(range(30, 36)))
    pickup = transport = None
    if complete:
        if any(p['pose'].get('set') is not True or type(p['pose'].get('z')) not in (int, float)
               or not math.isfinite(p['pose']['z']) for p in points):
            raise ValueError('All six captured arm heights must be finite')
        pickup = math.fsum(p['pose']['z'] / 6 for p in points)
        transport = pickup + 40
    session.update(pickup_height=pickup, transport_height=transport)
    draft.update(pickup_height=pickup, transport_height=transport)


class LessonStore:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.RLock()
        # Optical target memory is valid only in this live display activation.
        # Durable captures survive restart; this cache deliberately does not.
        self.marker_cache = None
        self.state = {'revision': 0, 'active_side': None, 'sessions': {}, 'pending_stops': {}, 'epoch': uuid.uuid4().hex}
        try:
            saved = json.loads(self.path.read_text())
            if not isinstance(saved, dict) or not isinstance(saved.get('sessions'), dict):
                raise ValueError('invalid calibration lesson store')
            self.state.update(saved)
            # Saved drafts survive. Live motion permissions never survive restart.
            self.state['epoch'] = uuid.uuid4().hex
            self.state['active_side'] = None
            self.state['active_id'] = None
            for session in self.state['sessions'].values():
                if session.get('stage') != 'complete':
                    set_capture_heights(session)
        except FileNotFoundError:
            pass

    def _save(self, state):
        state['revision'] += 1
        atomic_json(self.path, state)
        self.state = state

    def snapshot(self):
        with self.lock:
            value={'contract': 'hhh.cal2.session', 'version': 1, 'status': 'ready',
                   'observed_at': time.time(), **copy.deepcopy(self.state)}
            cache=self.marker_cache
            if cache:
                value['marker_preparation']={'id':cache['id'],'side':cache['side'],
                    'marker_positions':copy.deepcopy(cache['points']),
                    'reference_id':cache['reference_id'],
                    'movement_pending':bool(cache.get('movement')),
                    'notice':cache.get('notice'),
                    'ready':len(cache['points'])==6 and not cache.get('movement')
                            and -1<=time.time()-cache.get('frame_at',0)<=1.5}
                if cache['id']==self.state.get('active_id') and cache['side']==self.state.get('active_side'):
                    value['sessions'][cache['id']]['marker_positions']=copy.deepcopy(cache['points'])
            return value

    def clear_marker_cache(self):
        with self.lock:
            self.marker_cache=None

    def suspend_marker_observation(self):
        """An outage prevents capture but is not evidence that the camera moved."""
        with self.lock:
            if self.marker_cache:
                self.marker_cache.update(frame_at=0, movement=None)

    def _reset_marker_reference(self, cache, reason):
        # A moved camera invalidates both halves of every camera/arm pair and
        # the raised samples. Never combine old captures with new references.
        state=copy.deepcopy(self.state)
        session=state['sessions'].get(cache['id'])
        if session and session.get('stage') in ('points','perspective'):
            for point in session['draft']['points'].values():
                point.update(camera=None,pose={'set':False})
                point.pop('camera_observed_at',None)
                point.pop('camera_cached',None)
            session['draft']['parallax_points']={str(m):None for m in (31,35,33,34)}
            session.update(captures={},ground={},stage='points',camera_revision=None,
                           calibration_revision=None,arrivals=[],pickup_evidence=None,
                           reference_reset={'reason':reason,'at':time.time()})
            set_capture_heights(session)
            self._save(state)
        cache.update(points={},started_at=time.time(),frame_at=0,movement=None,
                     reference_id=uuid.uuid4().hex,notice=reason)

    def prepare_markers(self, side, session_id, layout):
        """Start optical preparation when targets load, before any motion grant."""
        with self.lock:
            key=[session_id,side,self.state['epoch'],layout]
            if not self.marker_cache or self.marker_cache['key']!=key:
                if self.marker_cache and self.marker_cache['id']==session_id:
                    self._reset_marker_reference(self.marker_cache,'Calibration board changed. Capture the six arm points again.')
                self.marker_cache={'key':copy.deepcopy(key),'id':session_id,'side':side,'points':{},
                                   'started_at':time.time(),'context':None,'reference_id':uuid.uuid4().hex}

    def observe_markers(self, side, session_id, context, frame_at, tags):
        """Freeze confirmed, currently visible targets as in Auto PP Cal 2."""
        with self.lock:
            cache=self.marker_cache
            if not cache or cache['id']!=session_id or cache['side']!=side:
                raise ValueError('calibration marker preparation has not started')
            if cache['context']!=context:
                if cache['context'] is not None:
                    self._reset_marker_reference(cache,'Camera source or correction changed. Capture the six arm points again.')
                cache['context']=copy.deepcopy(context)
            points=cache['points']
            if frame_at<=max(cache['started_at'],cache.get('frame_at',0)):return copy.deepcopy(points)
            cache['frame_at']=frame_at
            visible={}
            for tag in tags:
                marker=tag.get('id')
                if type(marker) is not int or marker not in range(30,36) or tag.get('missing',0)!=0:continue
                if not all(type(tag.get(k)) in (int,float) and math.isfinite(tag[k]) and 0<=tag[k]<=1 for k in ('nx','ny')):continue
                visible[str(marker)]={'u':tag['nx'],'v':tag['ny']}
            # Four separated targets must remain displaced by >4 pixels for
            # three distinct frames spanning 0.5 s. Single-tag projection onto
            # the arm, jitter and occlusion must never replace frozen points.
            size=context.get('size') or []
            if len(size)!=2 or any(type(n) not in (int,float) or not math.isfinite(n) or n<=0 for n in size):
                raise ValueError('valid camera dimensions required')
            moved={m:p for m,p in visible.items() if m in points
                   and _pixel_distance(p,points[m]['camera'],size)>4}
            movement=cache.get('movement')
            if len(moved)>=4 and _spread([points[m]['camera'] for m in moved]):
                stable=({m:p for m,p in moved.items() if m in movement['points']
                         and _pixel_distance(p,movement['points'][m],size)<=2} if movement else {})
                if len(stable)>=4 and _spread([points[m]['camera'] for m in stable]):
                    movement['frames']+=1
                    if movement['frames']>=3 and frame_at-movement['since']>=.5:
                        self._reset_marker_reference(cache,'Camera moved. References cleared; capture the six arm points again.')
                        return {}
                else:
                    cache['movement']={'points':moved,'since':frame_at,'frames':1}
            else:
                cache['movement']=None
            if not cache.get('movement'):
                for marker,camera in visible.items():
                    if marker not in points:
                        points[marker]={'camera':camera,'frame_at':frame_at}
            return copy.deepcopy(points)

    def check_marker_reference(self, measurement):
        """Reject a command measured just before another poll invalidated it."""
        with self.lock:
            cache=self.marker_cache
            if cache and cache.get('movement'):
                raise ValueError('Camera movement detected; waiting for stable calibration targets')
            if 'reference_id' in measurement and (not cache or measurement['reference_id']!=cache['reference_id']):
                raise ValueError('Camera references changed; capture again')

    def defer_stop(self, side, session_id):
        """Revoke lesson access durably before changing the projected screen."""
        with self.lock:
            state = copy.deepcopy(self.state)
            session = state['sessions'].get(session_id)
            if session:
                if session['side'] != side:
                    raise ValueError('session belongs to the other player')
                session.update(paused=True, access_until=0, releasing=True)
            state['pending_stops'][side] = session_id
            self._save(state)

    def confirm_stop(self, side, session_id):
        with self.lock:
            state = copy.deepcopy(self.state)
            if state['pending_stops'].get(side) == session_id:
                del state['pending_stops'][side]
                self._save(state)

    def begin(self, value, calibration):
        side, session_id = value.get('side'), value.get('id')
        if side not in ('green', 'purple') or not isinstance(session_id, str) or not 1 <= len(session_id) <= 160:
            raise ValueError('valid calibration side/session required')
        with self.lock:
            state = copy.deepcopy(self.state)
            if state['pending_stops']:
                raise PermissionError('Connect the arms to confirm the previous calibration stop before movement')
            if state['active_side'] is not None and state.get('active_id') != session_id:
                raise ValueError('the other player owns the unified playfield')
            session = state['sessions'].get(session_id)
            if session and session['side'] != side:
                raise ValueError('session belongs to the other player')
            if session and (session['player_id'] != value.get('player_id') or session['practice'] != bool(value.get('practice'))):
                raise ValueError('calibration session identity changed')
            if session is None:
                arm = copy.deepcopy(calibration['arms'][side])
                for point in arm['points'].values():
                    point.update(camera=None, pose={'set': False})
                arm['parallax_points'] = {str(marker): None for marker in (31,35,33,34)}
                session = {'id': session_id, 'side': side, 'player_id': value.get('player_id'),
                           'practice': bool(value.get('practice')), 'draft': arm, 'captures': {},
                           'ground': {}, 'stage': 'points', 'arrivals': [], 'calibration_revision': None,
                           'piece_ids':value.get('piece_ids',[]),'pickup_evidence':None}
                state['sessions'][session_id] = session
            if session['stage'] != 'complete':
                set_capture_heights(session)
            state['active_side'] = side
            state['active_id'] = session_id
            if 'display_camera_view' in value:
                session['display_camera_view'] = value['display_camera_view']
                session['draft']['camera_view'] = value['display_camera_view']
            session['activated_at'] = time.time()
            session['epoch'] = state['epoch']
            session['access_until'] = time.time() + 30
            session['paused'] = False
            session['releasing'] = False
            self._save(state)
            return self.snapshot()

    def _active(self, state, side, session_id, *, allow_paused=False):
        session = state['sessions'].get(session_id)
        if (state['active_side'] != side or state.get('active_id') != session_id or not session
                or session['side'] != side or session['epoch'] != state['epoch']):
            raise PermissionError('this calibration turn is not active')
        if (state['pending_stops'] or session.get('releasing')) and not allow_paused:
            raise PermissionError('Previous calibration stop is not confirmed')
        if not allow_paused and (session.get('paused') or session.get('access_until',0) < time.time()):
            raise PermissionError('calibration connection expired; reconnect before moving')
        return session

    def pause(self, side, session_id):
        with self.lock:
            state = copy.deepcopy(self.state)
            session = self._active(state, side, session_id, allow_paused=True)
            session['paused'] = True
            session['access_until'] = 0
            self._save(state)

    def heartbeat(self, side, session_id):
        with self.lock:
            if self.state['pending_stops']:
                raise PermissionError('Previous calibration stop is not confirmed')
            session = self._active(self.state, side, session_id, allow_paused=True)
            if session.get('releasing'):
                raise PermissionError('Calibration session is closing')
            session['paused'] = False
            session['access_until'] = time.time() + 30
            return self.snapshot()

    def capture(self, side, value, measurement):
        with self.lock:
            self.check_marker_reference(measurement)
            state = copy.deepcopy(self.state)
            session = self._active(state, side, value.get('id'))
            marker = value.get('marker')
            if type(marker) is not int or marker not in range(30,36):
                raise ValueError('select a marker from 30 to 35')
            point = next(p for p in session['draft']['points'].values() if p['marker'] == marker)
            camera, pose = measurement['camera'], measurement['pose']
            rig = measurement.get('camera_revision')
            if session.get('camera_revision') not in (None,rig):
                raise ValueError('camera correction changed; restart this calibration draft')
            session['camera_revision'] = rig
            if session.get('rig_identity') not in (None,measurement.get('rig_identity')):
                raise ValueError('arm connection changed; restart the draft')
            session['rig_identity']=measurement.get('rig_identity')
            if measurement['frame_at'] <= session.get('activated_at',0):
                raise ValueError('wait for a camera frame captured after the calibration targets loaded')
            if measurement['frame_at'] <= session['captures'].get(str(marker),0):
                raise ValueError('a fresh frame is required for recapture')
            for other in session['draft']['points'].values():
                if other is not point and other['pose'].get('set') and math.hypot(pose[0]-other['pose']['x'],pose[1]-other['pose']['y']) < 2:
                    raise ValueError('move the tool to a distinct calibration point')
            point.update(camera=camera, pose=dict(zip(('x','y','z','r'),pose), set=True))
            point['camera_observed_at']=measurement.get('marker_frame_at',measurement['frame_at'])
            point['camera_cached']=measurement.get('camera_cached',False)
            session['captures'][str(marker)] = measurement['frame_at']
            if marker in (31,35,33,34):
                session['ground'][str(marker)] = copy.deepcopy(measurement)
                session['draft']['parallax_points'][str(marker)] = None
            if len(session['captures']) == 6:
                session['stage'] = 'perspective'
            set_capture_heights(session)
            self._save(state)
            return self.snapshot()

    def parallax(self, side, value, measurement):
        marker = value.get('marker')
        if type(marker) is not int or marker not in (31,35,33,34):
            raise ValueError('outer perspective marker required')
        with self.lock:
            self.check_marker_reference(measurement)
            state = copy.deepcopy(self.state)
            session = self._active(state, side, value.get('id'))
            if session.get('camera_revision') != measurement.get('camera_revision'):
                raise ValueError('camera correction changed; restart calibration')
            if session.get('rig_identity') != measurement.get('rig_identity'):
                raise ValueError('arm connection changed; restart calibration')
            if len(session['captures']) != 6:
                raise ValueError('capture all six points first')
            if value.get('action') == 'ground':
                session['ground'][str(marker)] = measurement
            else:
                ground = session['ground'].get(str(marker))
                if not ground or measurement['frame_at'] <= ground['frame_at']:
                    raise ValueError('capture a ground view, then a fresh raised Atom view')
                session['draft']['parallax_points'][str(marker)] = {
                    'ground':ground['camera'], 'raised':measurement['camera'], 'height_mm':30, 'updated_at':time.time()}
            self._save(state)
            return self.snapshot()

    def _measured_session(self, state, side, session_id):
        """Read captured evidence without renewing an expired motion grant."""
        session=state['sessions'].get(session_id)
        if not session or session['side']!=side:
            raise PermissionError('calibration measurements belong to another turn')
        if self.marker_cache and self.marker_cache['id']==session_id:
            self.check_marker_reference({})
        return session

    def derive_heights(self, side, session_id, *, offline=False):
        with self.lock:
            state = copy.deepcopy(self.state)
            session = self._measured_session(state, side, session_id) if offline else self._active(state, side, session_id)
            set_capture_heights(session)
            if session['pickup_height'] is None:
                raise ValueError('Capture all six arm points to calculate heights')
            if state != self.state:
                self._save(state)
            return self.snapshot()

    def archive_rig(self, side, calibration):
        """Preserve a pre-existing rig before a validated lesson replaces it."""
        arm=calibration['arms'][side]
        if not any(p.get('pose',{}).get('set') for p in arm.get('points',{}).values()):
            return
        with self.lock:
            state=copy.deepcopy(self.state)
            identity=(calibration.get('saved_selection',{}).get(side) or {}).get('active_id') or 'rig:'+side+':'+str(calibration.get('revision',1))
            records=state.setdefault('saved_calibrations',{})
            if identity in records:return
            records[identity]={'id':identity,'side':side,'label':'Previous saved rig',
                               'revision':calibration.get('revision',1),'saved_at':arm.get('updated_at'),
                               'draft':copy.deepcopy(arm),'transport_height':arm.get('transport_height') if arm.get('transport_height') is not None else calibration.get('shared_z',{}).get('transport_height'),
                               'camera_revision':arm.get('camera_revision',calibration.get('camera_revision'))}
            self._save(state)

    def mark_committed(self, side, session_id, revision, *, offline=False):
        with self.lock:
            state = copy.deepcopy(self.state)
            session = self._measured_session(state, side, session_id) if offline else self._active(state, side, session_id)
            session.update(stage='tutorial', calibration_revision=revision, committed_at=time.time())
            record={'id':session_id+':'+str(revision),'side':side,'revision':revision,
                    'saved_at':session['committed_at'],'practice':session['practice'],
                    'draft':copy.deepcopy(session['draft']),'transport_height':session.get('transport_height'),
                    'camera_revision':session.get('camera_revision')}
            state.setdefault('saved_calibrations',{})[record['id']]=record
            self._save(state)

    def arrival(self, side, value, pose, target):
        with self.lock:
            state = copy.deepcopy(self.state)
            session = self._active(state, side, value.get('id'))
            if session['stage'] != 'tutorial' or len(session['arrivals']) >= 2:
                raise ValueError('complete calibration before the two guided moves')
            if math.dist(pose[:3], target[:3]) > 3:
                raise ValueError('move to the highlighted point before confirming arrival')
            session['arrivals'].append({'at':time.time(),'pose':pose})
            self._save(state)
            return self.snapshot()

    def observe_pickup(self, side, session_id, measurement, projected):
        with self.lock:
            state=copy.deepcopy(self.state)
            session=self._active(state,side,session_id)
            if session['stage']!='tutorial' or len(session['arrivals'])!=2: return self.snapshot()
            pose,pump=measurement['pose'],measurement['pump']
            evidence=session.get('pickup_evidence')
            if evidence is None:
                candidates=[tag for tag in projected.get('tags',[]) if tag.get('status')=='ready'
                            and tag['id'] in session['piece_ids'] and tag.get('pickup_z') is not None
                            and math.dist(pose[:3],[*tag['robot_xy'],tag['pickup_z']])<=8]
                if len(candidates)==1:
                    session['pickup_candidate']={'piece_id':candidates[0]['id'],'observed_at':measurement['feedback_at'],'pose':pose}
                candidate=session.get('pickup_candidate')
                if pump=='suck' and candidate and 0<=measurement['feedback_at']-candidate['observed_at']<=1.5 and math.dist(pose[:3],candidate['pose'][:3])<=8:
                    evidence={'piece_id':candidate['piece_id'],'pickup_at':measurement['feedback_at'],'pickup_pose':pose,'lifted_at':None}
                    session['pickup_evidence']=evidence
                    self._save(state)
                elif candidate:
                    # Keep the recent visible source in memory, so suction-tool
                    # occlusion cannot manufacture or lose the pickup proof.
                    self.state=state
            elif evidence and not evidence.get('lifted_at') and pump=='suck' and pose[2]>=evidence['pickup_pose'][2]+10 and measurement['feedback_at']>evidence['pickup_at']:
                evidence['lifted_at']=measurement['feedback_at'];evidence['lift_pose']=pose
                self._save(state)
            return self.snapshot()

    def finish(self, side, session_id, evidence_id):
        with self.lock:
            state = copy.deepcopy(self.state)
            session = self._active(state, side, session_id)
            if session['stage'] != 'tutorial' or len(session['arrivals']) != 2 or not (session.get('pickup_evidence') or {}).get('lifted_at'):
                raise ValueError('complete both guided moves, measured pickup and lift first')
            session.update(stage='complete', evidence_id=evidence_id, completed_at=time.time())
            # Reservation remains until the caller confirms stopped motion.
            self._save(state)
            return self.snapshot()

    def complete_measurements(self, side, session_id):
        """Completion receipt for the validated target measurements, not pickup proof."""
        with self.lock:
            state=copy.deepcopy(self.state)
            session=self._measured_session(state,side,session_id)
            if session['stage']=='complete':return self.snapshot()
            if (session['stage']!='tutorial' or type(session.get('calibration_revision')) is not int
                    or not session.get('committed_at') or len(session['captures'])!=6
                    or any(not session['draft']['parallax_points'].get(str(m)) for m in (31,35,33,34))
                    or any(type(session.get(k)) not in (int,float) or not math.isfinite(session[k]) for k in ('pickup_height','transport_height'))):
                raise ValueError('Save all six arm points, four raised samples and both heights first')
            session.update(stage='complete',completion_basis='measured-targets',completed_at=time.time(),
                           evidence_id='calibration:'+session_id+':'+str(session['calibration_revision']))
            self._save(state)
            return self.snapshot()

    def release(self, side, session_id):
        with self.lock:
            state = copy.deepcopy(self.state)
            session = state['sessions'].get(session_id)
            if session and session['side'] == side and state['active_side'] is None:
                if state.get('active_id') == session_id:
                    state['active_id'] = None
                    self._save(state)
                return self.snapshot()
            if not session or session.get('stage')!='complete':
                self._active(state, side, session_id, allow_paused=True)
            elif state.get('active_side') not in (None,side) or state.get('active_id') not in (None,session_id):
                raise PermissionError('another calibration owns the playfield')
            state['active_side'] = None
            state['active_id'] = None
            self.marker_cache = None
            self._save(state)
            return self.snapshot()
