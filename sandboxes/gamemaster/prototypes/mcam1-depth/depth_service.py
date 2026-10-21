"""Read-only MCAM1 + relay observer. Owns bounded histories and estimates."""
import base64
import copy
from collections import deque
import threading
import time
import cv2
import numpy as np
from depth_config import ATOM, ConfigStore
from depth_motion import PoseHistory, finite
from depth_geometry import camera_pose, lens_model, triangulate, translation_depth, fit_surface, clearance
from depth_vision import region_mask, attachment, LensCalibration
from depth_fusion import DepthFusion


class DepthService:
    def __init__(self, ctx, path, changed=lambda: None):
        self.ctx, self.store, self.changed = ctx, ConfigStore(path), changed
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.thread = None
        self.running = False
        self.poses = PoseHistory()
        self.pending = deque(maxlen=8)
        self.keys = deque(maxlen=24)
        self.fusion = DepthFusion()
        self.lens = LensCalibration()
        self.camera = self.motion = self.plane = self.measurement = None
        self.last_frame = None
        self.last_queued = 0.
        self.message = 'Start MCAM1 preview; video depth needs no camera setup'
        self.error = self.store.error

    def start_worker(self):
        self.thread = threading.Thread(target=self._loop, daemon=True, name='mcam1-depth')
        self.thread.start()

    def close(self):
        self.stop_event.set()
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout=3)
        with self.lock:
            self.running = False
            self._reset()
            self.camera = self.motion = None

    def _reset(self):
        self.poses.clear()
        self.pending.clear()
        self.keys.clear()
        self.fusion.clear()
        self.plane = self.measurement = None
        self.last_frame = None
        self.last_queued = 0.

    def configure(self, data):
        with self.lock:
            value = self.store.save(data)
            self._reset()
            self.error = None
            self.message = 'Configuration saved; collecting fresh observations'
        self.changed()
        return value

    def set_running(self, running):
        with self.lock:
            self.running = running
            self._reset()
            self.error = None
            self.message = 'Waiting for measured motion' if running else 'Analysis paused'
        self.changed()

    def _read(self, slug, function, contract):
        if not self.ctx.is_prototype_enabled(slug):
            raise ValueError(f'{slug} is disabled or unavailable')
        module = self.ctx.get_prototype(slug)
        output = getattr(module, function)()
        if (not isinstance(output, dict) or output.get('contract') != contract
                or type(output.get('version')) is not int or output['version'] != 1
                or output.get('status') != 'ready'):
            raise ValueError(f'{slug} has no compatible fresh input')
        return output

    def _loop(self):
        while not self.stop_event.is_set():
            started = time.monotonic()
            try:
                self.tick()
            except Exception as exc:
                with self.lock:
                    self._reset()
                    self.camera = self.motion = None
                    self.error = f'{type(exc).__name__}: {exc}'
                    self.message = 'Input unavailable'
            self.stop_event.wait(max(.005, (1/30 if self.running else .2)-(time.monotonic()-started)))

    def tick(self, now=None):
        # Public owner contracts only: these calls never open a camera or command an arm.
        frame = self._read('mcam1', 'still_snapshot', 'hhh.camera.still')
        # A producer can publish a new sample while its reader is running.
        # Measure age after each read, never against the beginning of the tick.
        observed_at = time.time() if now is None else now
        stamp, jpeg = frame.get('captured_at'), frame.get('image')
        width, height = frame.get('width'), frame.get('height')
        if (not finite(stamp) or not 0 <= observed_at-stamp <= .4 or not isinstance(jpeg, bytes)
                or not 4 <= len(jpeg) <= 2_000_000 or type(frame.get('frame_id')) is not int
                or type(width) is not int or type(height) is not int
                or (width, height) not in ((480, 320), (320, 240), (640, 480))
                or frame.get('mime_type') != 'image/jpeg' or frame.get('corrected') is not False):
            raise ValueError('MCAM1 frame is stale or malformed')
        with self.lock:
            config = self.store.value
            frame_key = (frame['frame_id'], stamp, width, height)
            if self.camera and (self.camera['width'], self.camera['height']) != (width, height):
                self._reset()
                self.lens = LensCalibration()
            self.camera = dict(width=width, height=height, frame_id=frame['frame_id'], received_at=stamp,
                               preview='data:image/jpeg;base64,'+base64.b64encode(jpeg).decode(), image=jpeg)
            try:
                relay = self._read('dobot-mg400-relay', 'arms_snapshot', 'hhh.relay.arms')
                observed_at = time.time() if now is None else now
                arm = relay.get('arms', {}).get(config['side'], {})
                previous_epoch = self.poses.epoch
                self.motion = self.poses.add(arm, observed_at)
                if previous_epoch is not None and previous_epoch != self.poses.epoch:
                    self.pending.clear()
                    self.keys.clear()
                    self.fusion.clear('Arm feedback generation changed')
                    self.plane = self.measurement = None
            except (ValueError, AttributeError, KeyError, TypeError) as exc:
                self.poses.clear()
                self.pending.clear()
                self.keys.clear()
                self.fusion.clear('Fresh measured arm feedback is required')
                self.motion = self.plane = self.measurement = None
                self.error = config['side'].title()+' arm: '+str(exc)
                return
            self.error = self.store.error
            if not self.running:
                return
            if self.last_frame and (stamp < self.last_frame[1] or frame['frame_id'] < self.last_frame[0]):
                self.pending.clear()
                self.keys.clear()
                self.fusion.clear('Camera sequence changed')
                self.plane = self.measurement = None
                self.last_queued = 0.
            if frame_key != self.last_frame and stamp-self.last_queued >= .08:
                self.last_frame, self.last_queued = frame_key, stamp
                self.pending.append(dict(stamp=stamp-config['frame_delay_ms']/1000, received_at=stamp,
                                         jpeg=jpeg, width=width, height=height, frame_id=frame['frame_id']))
            while self.pending:
                item = self.pending[0]
                pose = self.poses.at(item['stamp'])
                if pose is None:
                    if self.poses.samples and self.poses.samples[-1][0] < item['stamp'] and observed_at-item['received_at'] < .2:
                        break  # Wait for a measured sample after exposure; never extrapolate.
                    self.pending.popleft()
                    self.message = 'Waiting for feedback that brackets the frame timestamp'
                    continue
                self.pending.popleft()
                self._process(item, pose, observed_at)

    def _process(self, item, pose, now):
        config = self.store.value
        decoded = cv2.imdecode(np.frombuffer(item['jpeg'], np.uint8), cv2.IMREAD_GRAYSCALE)
        if decoded is None or decoded.shape != (item['height'], item['width']):
            raise ValueError('Decoded MCAM1 dimensions do not match its contract')
        matrix, distortion, source = lens_model(config, item['width'], item['height'])
        current = dict(gray=decoded, pose=pose, stamp=item['stamp'], speed=self.motion['speed_mm_s'], frame_id=item['frame_id'])
        if self.fusion.last_stamp is not None and item['stamp']-self.fusion.last_stamp > .5:
            self.fusion.clear('Video tracking gap; collecting fresh viewpoints')
            self.keys.clear()
        automatic = not config['mounting_confirmed']
        rotation, centre = camera_pose(pose, config)
        candidates = []
        references = list(self.keys)
        if self.fusion.reference is not None and all(old is not self.fusion.reference for old in references):
            references.append(self.fusion.reference)
        for old in references:
            old_rotation, old_centre = camera_pose(old['pose'], config)
            baseline = float(np.linalg.norm(pose[:3]-old['pose'][:3]) if automatic else np.linalg.norm(centre-old_centre))
            angular = (abs((pose[3]-old['pose'][3]+180)%360-180) if automatic else
                       np.degrees(np.arccos(np.clip((np.trace(rotation.T@old_rotation)-1)/2, -1, 1))))
            if config['min_baseline_mm'] <= baseline <= 40 and 0 < item['stamp']-old['stamp'] <= 4 and angular < (.15 if automatic else .75):
                candidates.append((abs(baseline-20), baseline, old))
        if not self.keys or np.linalg.norm(pose[:3]-self.keys[-1]['pose'][:3]) >= 1 or item['stamp']-self.keys[-1]['stamp'] >= .2:
            self.keys.append(current)
        if not candidates:
            if self.fusion.reference is None:
                self.fusion.begin(current, matrix, distortion, config['atom_roi'])
            self.fusion.track(decoded, item['stamp'])
            self.message = 'Waiting for 10–40 mm of translation with little rotation' if config['min_baseline_mm'] == 10 else 'Waiting for a sufficient translation baseline'
            return
        # Keep feature identities tied to one reference during the sweep. Picking
        # a different "best" pair every frame would discard accumulated evidence.
        retained = next((row for row in candidates if row[2] is self.fusion.reference), None)
        _, baseline, reference = retained or min(candidates, key=lambda row: row[0])
        timing_motion = max(self.motion['speed_mm_s'], reference['speed'])*config['timing_uncertainty_ms']/1000
        if timing_motion > min(2, baseline*.15):
            self.message = 'Timing uncertainty is too large for this speed; slow down or calibrate timing'
            self.measurement = self.plane = None
            return
        if self.fusion.reference is not reference:
            self.fusion.begin(reference, matrix, distortion, config['atom_roi'])
        a, b, track_ids = self.fusion.track(decoded, item['stamp'])
        if len(a) < 8:
            self.measurement = None
            self.fusion.clear('Scene features lost; rebuilding feature identities')
            self.keys.clear()
            self.keys.append(current)
            self.message = 'Too few stable scene features; use a sharp image and textured stationary objects'
            return
        if automatic:
            world, pixels, depths, residual, geometry = translation_depth(a, b, baseline, matrix, distortion, details=True)
        else:
            world, pixels, depths, residual, geometry = triangulate(a, b, reference['pose'], pose, config, matrix, distortion, details=True)
        if len(world) < 8:
            self.measurement = None
            self.message = 'No reliable scene depth yet; translate sideways with little rotation'
            return
        camera_points, pixels, evidence = self.fusion.update(
            track_ids, pixels, geometry, residual, frame_key=(item['frame_id'], item['stamp']),
            stamp=item['stamp'], baseline=baseline, timing_motion=timing_motion, tracked_count=len(a),
            view_position=pose[:3] if automatic else centre)
        if len(camera_points) < 8:
            self.measurement = None
            self.message = 'Scene observations disagree; keep a steady camera and stationary textured features in view'
            return
        depths = camera_points[:, 2]
        world = camera_points if automatic else camera_points@rotation.T+centre
        surface_mask = region_mask(decoded.shape, config['surface_roi'], config['atom_roi'])
        surface = surface_mask[pixels[:, 1].astype(int), pixels[:, 0].astype(int)] > 0
        plane_message = ('Automatic motion scale; distances use the nominal lens and a rigid camera with steady orientation'
                         if automatic else 'Select a screen region to also measure Atom clearance')
        if automatic:
            self.plane = None  # Camera coordinates are not a calibrated world/contact plane.
        elif config['surface_roi']:
            try:
                plane, _ = fit_surface(world[surface])
                plane['updated_at'] = item['stamp']
                self.plane = plane
                plane_message = 'Screen tracked; clearance assumes an upright Atom centred under the suction contact'
            except ValueError as exc:
                plane_message = str(exc)
        screen_tracks = surface_mask[b[:, 1].astype(int), b[:, 0].astype(int)] > 0
        shift = float(np.median(np.linalg.norm(b[screen_tracks]-a[screen_tracks], axis=1))) if screen_tracks.any() else 0.
        attached = attachment(reference['gray'], decoded, config['atom_roi'],
                              shift, self.motion['pump_mode'])
        distances = np.linalg.norm(camera_points, axis=1)
        points = [dict(x=round(float(p[0])/item['width'], 5), y=round(float(p[1])/item['height'], 5),
                       depth_mm=round(float(z), 1), distance_mm=round(float(distance), 1), **support)
                  for p, z, distance, support in zip(pixels, depths, distances, evidence)]
        self.measurement = dict(frame_id=item['frame_id'], received_at=item['received_at'], points=points,
                                width=item['width'], height=item['height'], grid_step_px=12,
                                distance_kind='lens_to_point', scene_points=len(points),
                                method='automatic_motion' if automatic else 'configured_motion',
                                fusion=copy.deepcopy(self.fusion.stats),
                                captured_at_estimate=item['stamp'],
                                preview='data:image/jpeg;base64,'+base64.b64encode(item['jpeg']).decode(),
                                baseline_mm=round(baseline, 2), interval_ms=round((item['stamp']-reference['stamp'])*1000),
                                reprojection_px=round(float(np.median(residual)), 3),
                                timing_motion_mm=round(timing_motion, 2), lens_source=source,
                                attachment=attached, sample_pose=pose.tolist())
        self.message = f"{len(points)} scene depth samples; {self.fusion.stats['combined_points']} combined across repeated viewpoints. "+plane_message

    def calibration(self, action, columns=9, rows=6, square=10):
        with self.lock:
            if action == 'clear_samples':
                self.lens = LensCalibration()
            elif action == 'clear_intrinsics':
                self.configure({**self.store.value, 'intrinsics': None})
            elif action == 'solve':
                lens = self.lens.solve()
                self.configure({**self.store.value, 'intrinsics': lens})
            elif action == 'capture':
                if not self.camera or not 0 <= time.time()-self.camera['received_at'] <= .4:
                    raise ValueError('A fresh MCAM1 preview is required')
                gray = cv2.imdecode(np.frombuffer(self.camera['image'], np.uint8), cv2.IMREAD_GRAYSCALE)
                if gray is None:
                    raise ValueError('Invalid camera image')
                self.lens.capture(gray, columns, rows, square)
            else:
                raise ValueError('Unknown calibration action')
        self.changed()

    def snapshot(self, now=None):
        with self.lock:
            now = time.time() if now is None else now
            camera = self.camera if self.camera and 0 <= now-self.camera['received_at'] <= .4 else None
            motion = self.motion if self.motion and 0 <= now-self.motion['feedback_at'] <= .25 else None
            usable = self.running and camera is not None and motion is not None and not self.error
            plane = self.plane if usable and self.plane and 0 <= now-self.plane['updated_at'] <= 3 else None
            measure = (self.measurement if usable and self.measurement
                       and 0 <= now-self.measurement['captured_at_estimate'] <= .5 else None)
            attached = (measure['attachment'] if measure and 0 <= now-measure['captured_at_estimate'] <= .5
                        else dict(state='unknown', reason='Fresh movement evidence is required'))
            result = dict(contract='hhh.mcam1.depth', version=1, status='ready' if plane or measure else 'unavailable',
                          automatic_motion_supported=True,
                          temporal_fusion_supported=True,
                          observed_at=now, running=self.running, config=copy.deepcopy(self.store.value), atom=ATOM.copy(),
                          message=self.message, error=self.error, calibrated_lens=self.store.value['intrinsics'] is not None,
                          camera={k:v for k,v in camera.items() if k != 'image'} if camera else None,
                          motion=copy.deepcopy(motion), plane=copy.deepcopy(plane), measurement=copy.deepcopy(measure),
                          attachment=copy.deepcopy(attached), clearance_if_held_mm=None,
                          lens_samples=len(self.lens.samples), quality='experimental',
                          timing_source='MCAM1 host receipt minus configured delay; exposure timing unverified')
            if plane:
                result['clearance_if_held_mm'] = round(clearance(motion['pose'], plane, self.store.value), 2)
                result['plane_age_ms'] = round((now-plane['updated_at'])*1000)
            if not camera:
                result['message'] = 'MCAM1 unavailable; start its preview in the MCAM1 tab'
            elif not motion:
                result['message'] = 'Selected arm feedback is unavailable'
            elif not plane and measure is None and self.plane:
                result['message'] = 'Surface estimate expired; translate the camera to observe it again'
            return result
