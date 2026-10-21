"""Game-owned delivery of authoritative progress, with a durable result outbox."""
import json
import os
from pathlib import Path
import threading
import time


class ProgressLink:
    def __init__(self, module_reader, engine_reader, wake, path, result_listener=None, tick=None):
        self.module_reader = module_reader
        self.engine_reader = engine_reader
        self.wake = wake
        self.path = Path(path)
        self.result_listener, self.tick = result_listener, tick
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.thread = None
        self.attempt = None
        self.pending = None
        self.recovered = False
        self.last_checkpoint = 0
        self.sequence = 0
        self.state = {'status': 'unavailable', 'error': 'not initialized', 'result': None}

    def _set(self, **values):
        state = {**self.state, **values}
        if state != self.state:
            self.state = state
            self.wake()

    def _module(self):
        module = self.module_reader('photon-progress')
        if module is None or not callable(getattr(module, 'progress_snapshot', None)):
            raise ValueError('Photon Progress is unavailable or disabled')
        return module

    @staticmethod
    def _check(value):
        if not isinstance(value, dict) or value.get('contract') != 'photon.progress' or type(value.get('version')) is not int or value['version'] != 2:
            raise ValueError('Photon Progress contract mismatch (expected photon.progress v2)')
        if value.get('status') != 'ready':
            raise ValueError(value.get('error') or 'Photon Progress unavailable')
        return value

    def _recover(self):
        if self.recovered:
            return
        module = self._module()
        self._check(module.progress_snapshot())
        if self.path.exists():
            pending = json.loads(self.path.read_text())
            result = self._check(module.finalize_attempt(pending))
            if self.result_listener:
                self.result_listener(result['attempt'])
            self.path.unlink()
        self._check(module.recover_attempts())
        self.recovered = True

    def roster(self):
        with self.lock:
            self._recover()
            return self._check(self._module().progress_snapshot())

    def begin(self, value):
        with self.lock:
            self._recover()
            if self.attempt or self.pending:
                raise ValueError('previous result is awaiting save')
            result = self._check(self._module().begin_attempt(value))
            self.attempt = result['attempt']
            self.sequence = self.attempt['sequence']
            self.last_checkpoint = time.monotonic()
            self._set(status='ready', error=None, result=None, run_id=value['run_id'],
                      reward_enabled=self.attempt['reward_enabled'], banked_kills=0,
                      participants=self.attempt['participants'], metadata=self.attempt['metadata'])
            return self.attempt

    def _write_pending(self, value):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix('.tmp')
        with temp.open('w') as handle:
            json.dump(value, handle, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, self.path)
        descriptor = os.open(self.path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def flush(self, outcome=None):
        with self.lock:
            if not self.attempt and not self.pending:
                return
            engine = self.engine_reader()
            if engine is None:
                raise ValueError('active attempt has no simulation')
            with engine.lock:
                phase, kills = engine.phase, engine.kills
                seconds = engine.sim_time
                released = engine.next_enemy_id - 1
                reward=engine.rewards.checkpoint(final=phase in ('won','overrun','operator_ended') or outcome is not None,outcome=outcome) if hasattr(engine,'rewards') else None
                telemetry=json.loads(json.dumps(getattr(engine,'telemetry',{})))
                heatmap=engine.rewards.heatmap.snapshot() if hasattr(getattr(engine,'rewards',None),'heatmap') else None
                movement=engine.robot_movement.snapshot(engine.sim_time) if (phase in ('won','overrun','operator_ended') or outcome is not None) and hasattr(engine,'robot_movement') else None
            final = phase in ('won', 'overrun', 'operator_ended') or outcome is not None
            if not self.pending:
                if not final and time.monotonic() - self.last_checkpoint < 30:
                    return
                self.sequence += 1
                value = {'run_id': self.attempt['run_id'], 'kills': kills, 'sequence': self.sequence}
                if self.attempt['metadata'].get('reward_rules') is not None:
                    value['reward']=reward
                if final:
                    value.update(outcome=phase if phase in ('won', 'overrun', 'operator_ended') else outcome,
                                 active_seconds=seconds, finished_at=time.time(), released_orcs=released,telemetry=telemetry)
                    if heatmap is not None:value['kill_heatmap']=heatmap
                    if movement is not None:value['robot_movement']=movement
                    self.pending = value
            else:
                value = self.pending
                final = True
            try:
                # Persist the terminal result even when Progress is offline.
                if final:
                    self._write_pending(value)
                module = self._module()
                # Validate producer output before invoking any mutation.
                self._check(module.progress_snapshot())
                if final:
                    result = self._check(module.finalize_attempt(value))
                    if self.result_listener:
                        self.result_listener(result['attempt'])
                    self.path.unlink()
                    self.pending = None
                    self.attempt = None
                    self._set(status='ready', error=None, banked_kills=kills, result=result['attempt'])
                else:
                    result = self._check(module.checkpoint_attempt(value))
                    self.last_checkpoint = time.monotonic()
                    self._set(status='ready', error=None, banked_kills=result['attempt']['kills'])
            except Exception as exc:
                self._set(status='unavailable', error=f'Result pending save: {exc}')
                raise ValueError(self.state['error']) from exc

    def _run(self):
        while not self.stop_event.wait(.25):
            try:
                with self.lock:
                    self._recover()
                    if self.attempt or self.pending:
                        self.flush()
                    elif self.state['status'] != 'ready':
                        self._check(self._module().progress_snapshot())
                        self._set(status='ready', error=None)
            except Exception as exc:
                with self.lock:
                    self._set(status='unavailable', error=str(exc))
            # Display ownership and its safety lease must still be maintained
            # when a pending score cannot yet be recovered.
            if self.tick:
                try:
                    self.tick()
                except Exception as exc:
                    with self.lock:
                        self._set(status='unavailable', error=f'Game journey: {exc}')

    def start(self):
        self.stop_event.clear()
        if self.thread is None or not self.thread.is_alive():
            self.thread = threading.Thread(target=self._run, name='photon-game-progress', daemon=True)
            self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=3)
            self.thread = None
        self.recovered = False
        # An old in-memory engine must never be checkpointed after restart.
        self.attempt = None
        self.pending = None

    def snapshot(self):
        with self.lock:
            return json.loads(json.dumps(self.state))

    def clear_finished(self):
        with self.lock:
            if self.attempt or self.pending:
                raise ValueError('previous result is awaiting save')
            self._set(status='ready', error=None, result=None, run_id=None, participants=[],
                      metadata={}, reward_enabled=False, practice_reason=None, banked_kills=0)
