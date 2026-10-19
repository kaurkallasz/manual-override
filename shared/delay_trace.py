"""Opt-in timing recorder shared by producers; imports start no threads or I/O.

Public contract: delay.analysis v1. Mobile LTZ API owns lifecycle and HTTP access.
Producers never wait for storage or the reader lock. Full buffers drop records.
Only named timings and allowlisted numeric/identity fields are collected.
"""
from collections import deque
from contextlib import nullcontext
from functools import wraps
import json
import math
import os
from pathlib import Path
import re
import threading
import time
import uuid
from shared.delay_evidence import clean as clean_evidence, safe_text, add_timing, operation_summary

CONTRACT = 'delay.analysis'
VERSION = 1
QUEUE_LIMIT = 8192
RECORD_LIMIT = 20000
FILE_LIMIT = 650 * 1024 * 1024
WINDOW_S = 60
PRE_INCIDENT_S = 10
POST_INCIDENT_S = 5
FAST_LOCK_MS = 1
CHECKPOINT_S = 5
_OFF = nullcontext()
_local = threading.local()
_recorder = None
_remote = None
_remote_events = deque(maxlen=512)
_remote_dropped = 0
_remote_until = 0
_remote_control = {}
_META = ('side', 'run_id', 'sequence', 'frame_at', 'feedback_at', 'feedback_age_ms', 'lock_id',
         'source_gap_ms', 'motion_epoch', 'bytes', 'hidden', 'clock', 'client_id')


def enabled():
    return bool((_recorder and _recorder.recording) or (_remote and time.monotonic() < _remote_until))


def config(side=None):
    r = _recorder
    return {'contract': CONTRACT, 'version': VERSION,
            'capture_id': r.capture_id if r else None, 'revision': r.revision if r else 0,
            'recording': bool(r and r.recording and (r.side == 'both' or side in (None, r.side))),
            'lease_ms': 4000}


def annotate(**values):
    stack = getattr(_local, 'stack', ())
    if stack:
        stack[-1].meta.update({k: v for k, v in values.items() if k in _META and
                              (v is None or type(v) in (int, bool) or type(v) is float and math.isfinite(v)
                               or isinstance(v, str) and len(v) <= 96)})


def context():
    stack = getattr(_local, 'stack', ())
    if not stack:
        return None
    parent = stack[-1]
    return {'capture_id': parent.capture_id, 'id': parent.id, 'trace_id': parent.trace, 'meta': parent.meta}


def _submit(event):
    global _remote_dropped
    r = _recorder
    if r:
        try:
            r.submit(event)
        except Exception:
            r.observer_errors += 1
    elif _remote and event['capture_id'] == _remote['capture_id']:
        if len(_remote_events) == _remote_events.maxlen:
            _remote_dropped += 1
        _remote_events.append(event)


class Span:
    def __init__(self, name, side=None):
        self.name, self.side = name, side

    def __enter__(self):
        r = _recorder
        self.capture_id = r.capture_id if r else (_remote or {}).get('capture_id')
        stack = getattr(_local, 'stack', None)
        if stack is None:
            stack = _local.stack = []
        parent = stack[-1] if stack and stack[-1].capture_id == self.capture_id else None
        self.id = uuid.uuid4().hex
        self.parent = parent.id if parent else None
        self.trace = parent.trace if parent else self.id
        self.meta = dict(parent.meta) if parent else {}
        inherited = getattr(_local, 'inherited', None)
        if not parent and inherited and inherited.get('capture_id') == self.capture_id:
            self.parent = inherited['id']
            self.trace = inherited['trace_id']
            self.meta.update(inherited['meta'])
        if self.side in ('green', 'purple'):
            self.meta['side'] = self.side
        self.children = 0
        self.started = time.perf_counter_ns()
        self.cpu = time.thread_time_ns()
        stack.append(self)
        return self

    def __exit__(self, typ, value, tb):
        elapsed = time.perf_counter_ns() - self.started
        cpu = time.thread_time_ns() - self.cpu
        stack = _local.stack
        stack.pop()
        if stack and stack[-1].capture_id == self.capture_id:
            stack[-1].children += elapsed
        _submit({'capture_id': self.capture_id, 'id': self.id, 'parent_id': self.parent,
                 'trace_id': self.trace, 'name': self.name, 'kind': 'span',
                 'start_ms': self.started / 1e6, 'duration_ms': elapsed / 1e6,
                 'self_ms': max(0, elapsed - self.children) / 1e6, 'cpu_ms': cpu / 1e6,
                 'source': _remote['source'] if _remote else 'hub', 'pid': os.getpid(),
                 'thread': threading.current_thread().name, 'clock': 'host-monotonic',
                 'error': typ.__name__ if typ else None, **self.meta})
        return False


def span(name, *, side=None):
    return Span(name, side) if enabled() else _OFF


def traced(name, *, side=None):
    def decorate(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if not enabled():
                return fn(*args, **kwargs)
            owner = side
            if side == 'argument':
                owner = kwargs.get('side', args[0] if args and isinstance(args[0], str) else None)
            elif side == 'self':
                owner = getattr(args[0], 'side', None)
            with span(name, side=owner):
                return fn(*args, **kwargs)
        return wrapped
    return decorate


def call(name, fn, *args, **kwargs):
    if not enabled():
        return fn(*args, **kwargs)
    with span(name):
        return fn(*args, **kwargs)


def measure(name, duration_ms, **meta):
    if not enabled() or not math.isfinite(duration_ms) or duration_ms < 0:
        return
    r = _recorder
    stack = getattr(_local, 'stack', ())
    parent = stack[-1] if stack else None
    _submit({'capture_id': r.capture_id if r else (_remote or {}).get('capture_id'),
             'id': uuid.uuid4().hex, 'parent_id': None, 'trace_id': parent.trace if parent else None,
             'name': name, 'kind': 'gauge', 'start_ms': time.perf_counter_ns()/1e6,
             'duration_ms': duration_ms, 'self_ms': None, 'cpu_ms': None,
             'source': _remote['source'] if _remote else 'hub', 'pid': os.getpid(),
             'thread': threading.current_thread().name, 'clock': 'host-monotonic',
             **{k: v for k, v in meta.items() if k in _META}})


def evidence(name, details, *, side=None, incident=False):
    """Passive, allowlisted decision evidence using the existing producer queue."""
    if not enabled():
        return
    try:
        r = _recorder
        _submit({'capture_id': r.capture_id if r else (_remote or {}).get('capture_id'),
                 'id': uuid.uuid4().hex, 'name': name, 'kind': 'evidence', 'duration_ms': 0,
                 'start_ms': time.perf_counter_ns()/1e6, 'clock': 'host-monotonic',
                 'source': _remote['source'] if _remote else 'hub', 'side': side,
                 'details': clean_evidence(details), 'incident': incident})
    except Exception:
        if _recorder:
            _recorder.observer_errors += 1


class TimedLock:
    """Same lock and acquisition semantics, with separately named wait/hold spans."""
    def __init__(self, lock, name):
        self.lock, self.name = lock, name

    def __enter__(self):
        with span(self.name + '.wait'):
            annotate(lock_id=hex(id(self.lock)))
            self.lock.acquire()
        self.hold = span(self.name + '.hold')
        self.hold.__enter__()
        annotate(lock_id=hex(id(self.lock)))
        return self

    def __exit__(self, *exc):
        try:
            return self.hold.__exit__(*exc)
        finally:
            self.lock.release()


def locked(lock, name):
    return TimedLock(lock, name) if enabled() else lock


def remote_config(control, source):
    """Worker control rides existing IPC; expiry prevents a stranded recorder."""
    global _remote, _remote_until, _remote_control
    if not isinstance(control, dict) or control.get('contract') != CONTRACT or control.get('version') != VERSION:
        return
    _remote_control = control
    _local.inherited = control.get('parent')
    if not control.get('recording'):
        _remote = None
        _remote_events.clear()
        return
    if not _remote or _remote['capture_id'] != control.get('capture_id'):
        _remote_events.clear()
    _remote = {**control, 'source': source}
    _remote_until = time.monotonic() + 4


def remote_batch():
    global _remote_dropped
    events = []
    while _remote_events and len(events) < 128:
        events.append(_remote_events.popleft())
    value = {'events': events, 'dropped': _remote_dropped, 'capture_id': _remote_control.get('capture_id'),
             'recording': bool(_remote and time.monotonic() < _remote_until), 'revision': _remote_control.get('revision')}
    _remote_dropped = 0
    return value


def accept_remote(batch, source):
    r = _recorder
    if r and isinstance(batch, dict) and batch.get('capture_id') == r.capture_id and r.capture_id:
        r.worker_seen(source, batch.get('dropped', 0), batch.get('recording', False), batch.get('revision'))
        for event in batch.get('events', [])[:128]:
            r.submit({**event, 'source': source})


class Recorder:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.recording = False
        self.capture_id = None
        self.revision = 0
        self.side = 'both'
        self.started_at = self.started_mono = self.deadline = 0
        self.queue = deque()
        self.queue_lock = threading.Lock()
        self.data_lock = threading.RLock()
        self.control_lock = threading.Lock()
        self.events = deque(maxlen=RECORD_LIMIT)
        self.operations = {}
        self.incidents = deque(maxlen=256)
        self.participants = {}
        self.dropped = self.expired = self.received = self.written = 0
        self.storage_error = None
        self.observer_errors = 0
        self.coverage_dropped = 0
        self.path = None
        self.stop_reason = None
        self.stopped_mono = 0
        self.detail_until = 0
        self.detail_truncated = False
        self.detail_omitted = self.fast_locks_aggregated = self.incidents_evicted = 0
        self.saved_ids = set()
        self.saved_order = deque()
        self.last_auto_incident = 0
        self.last_explicit_incident = {}
        self.last_checkpoint = 0
        self.checkpoint_signature = None
        self.summary_path = None
        self.summary_bytes = 0
        self._restore()
        self._closed = threading.Event()
        self._thread = threading.Thread(target=self._collect, name='delay-analysis', daemon=True)
        self._thread.start()

    def start(self, *, side='both', seconds=0):
        if side not in ('both', 'green', 'purple') or type(seconds) is not int or not (seconds == 0 or 10 <= seconds <= 1800):
            raise ValueError('Choose both/green/purple and 0 (until stopped) or 10–1800 seconds.')
        with self.control_lock:
            if self.recording or self.queue:
                raise ValueError('Stop the current recording and wait for its buffer to drain first.')
            self._checkpoint(force=True)
            self.directory.mkdir(parents=True, exist_ok=True)
            capture = uuid.uuid4().hex
            path = self.directory / (capture + '.jsonl')
            # Fail start explicitly if storage is unavailable, before enabling hooks.
            path.write_text(json.dumps({'contract': CONTRACT, 'version': VERSION, 'capture_id': capture,
                                       'kind': 'capture', 'started_at': time.time(), 'side': side}) + '\n')
            for old in sorted(self.directory.glob('*.jsonl'), key=lambda p: p.stat().st_mtime)[:-3]:
                if re.fullmatch(r'[a-f0-9]{32}\.jsonl', old.name):
                    old.unlink()
                    old.with_suffix('.summary.json').unlink(missing_ok=True)
            with self.data_lock:
                self.events.clear(); self.operations.clear(); self.incidents.clear(); self.participants.clear()
                self.dropped = self.expired = self.received = 0
                self.written = path.stat().st_size
                self.capture_id, self.path, self.side = capture, path, side
                self.summary_path = path.with_suffix('.summary.json')
                self.started_at, self.started_mono = time.time(), time.monotonic()
                self.deadline = self.started_mono + seconds if seconds else 0
                self.storage_error = self.stop_reason = None
                self.stopped_mono = 0
                self.detail_until = self.last_auto_incident = self.last_checkpoint = 0
                self.detail_truncated = False
                self.detail_omitted = self.fast_locks_aggregated = self.incidents_evicted = 0
                self.saved_ids.clear(); self.saved_order.clear()
                self.last_explicit_incident.clear()
                self.checkpoint_signature = None
                self.summary_bytes = self.observer_errors = self.coverage_dropped = 0
                self.revision += 1
                self.recording = True
            try:
                self._checkpoint(force=True)
            except OSError as exc:
                self.storage_error = type(exc).__name__ + ': ' + str(exc)
                self.stop('recorder_error')
                raise
        return config()

    def stop(self, reason='operator'):
        if not self.recording:
            return config()
        self.stopped_mono = time.monotonic()
        self.recording = False
        self.stop_reason = reason
        self.revision += 1
        return config()

    def clear(self):
        with self.control_lock:
            if self.recording or self.queue:
                raise ValueError('Stop recording and wait for the buffer to drain before clearing.')
            with self.data_lock:
                if self.path:
                    self.path.unlink(missing_ok=True)
                if self.summary_path:
                    self.summary_path.unlink(missing_ok=True)
                self.events.clear(); self.operations.clear(); self.incidents.clear(); self.participants.clear()
                self.capture_id = self.path = None
                self.dropped = self.expired = self.received = self.written = 0
                self.summary_path = None
                self.summary_bytes = self.detail_omitted = self.fast_locks_aggregated = self.incidents_evicted = 0
                self.detail_truncated = False
                self.storage_error = self.stop_reason = None
                self.saved_ids.clear(); self.saved_order.clear()

    def submit(self, event, *, final=False):
        if (not self.recording and not final) or event.get('capture_id') != self.capture_id:
            return
        if self.side != 'both' and event.get('side') not in (None, self.side):
            return
        if not self.queue_lock.acquire(False):
            self.dropped += 1
            return
        try:
            if event.get('capture_id') != self.capture_id or not self.recording and not final:
                return
            if len(self.queue) >= QUEUE_LIMIT:
                self.dropped += 1
            else:
                self.queue.append(event)
        finally:
            self.queue_lock.release()

    def worker_seen(self, source, dropped=0, recording=False, revision=None):
        # Runs on the existing feedback path: never wait for a dashboard reader.
        if not self.data_lock.acquire(False):
            self.coverage_dropped += 1
            return
        try:
            if source not in self.participants and len(self.participants) >= 32:
                self.coverage_dropped += 1
                return
            dropped += self.participants.get(source, {}).get('dropped', 0)
            self.participants[source] = {'source': source, 'seen_at': time.time(),
                                         'recording': recording, 'revision': revision, 'dropped': dropped}
        finally:
            self.data_lock.release()

    def client_batch(self, side, value):
        if not isinstance(value, dict) or value.get('contract') != CONTRACT or type(value.get('version')) is not int or value['version'] != VERSION:
            raise ValueError('Expected delay.analysis v1.')
        client_id = value.get('client_id')
        rows = value.get('events')
        if not isinstance(client_id, str) or not re.fullmatch(r'[a-f0-9]{32}', client_id) or not isinstance(rows, list) or len(rows) > 100:
            raise ValueError('Invalid client timing batch.')
        if value.get('capture_id') != self.capture_id:
            return config(side)
        if type(value.get('revision')) is not int or value['revision'] != self.revision:
            return config(side)
        source = side + '/browser/' + client_id
        with self.data_lock:
            if source not in self.participants and len(self.participants) >= 32:
                raise ValueError('Too many diagnostic participants.')
            previous = self.participants.get(source, {})
            stop_ack = value.get('recording') is False and previous.get('recording') is True
            final = (stop_ack and not self.recording and previous.get('recording') is True
                     and time.time() - previous.get('seen_at', 0) <= 10)
            if not stop_ack and time.monotonic() - previous.get('received_mono', -10) < .2:
                raise ValueError('Diagnostic batch rate exceeded.')
        validated = []
        for row in rows:
            if not isinstance(row, dict) or row.get('name') not in CLIENT_OPERATIONS:
                raise ValueError('Unknown browser timing operation.')
            start, duration = row.get('start_ms'), row.get('duration_ms')
            if any(type(v) not in (int, float) or not math.isfinite(v) for v in (start, duration)) or not 0 <= duration <= 120000 or start < 0:
                raise ValueError('Invalid browser duration.')
            gateway = row['name'].startswith('gateway.')
            gauge = gateway or row['name'] in ('browser.feedback_age', 'browser.frame_gap', 'browser.receive_gap', 'browser.event_loop_lag')
            event = {'capture_id': self.capture_id, 'id': uuid.uuid4().hex, 'parent_id': None,
                     'trace_id': None, 'source': source, 'thread': 'browser', 'clock': 'client-monotonic',
                     'side': side, 'name': row['name'], 'kind': 'gauge' if gauge else 'span', 'start_ms': start,
                     'duration_ms': duration, 'self_ms': None, 'cpu_ms': None,
                     'client_id': client_id, 'received_at': time.time()}
            for key in ('sequence', 'hidden', 'feedback_age_ms', 'run_id'):
                item = row.get(key)
                if item is None or type(item) in (bool, int) or isinstance(item, str) and len(item) <= 96 or type(item) is float and math.isfinite(item):
                    event[key] = item
            validated.append(event)
        with self.data_lock:
            self.participants[source] = {'source': source, 'seen_at': time.time(), 'received_mono': time.monotonic(),
                                         'recording': value.get('recording') is True, 'revision': value.get('revision'),
                                         'dropped': max(0, min(1000000000, value['dropped'])) if type(value.get('dropped')) is int else 0}
        for event in validated:
            self.submit(event, final=final)
        return config(side)

    def mark(self, label='Operator marked incident'):
        if not self.recording:
            raise ValueError('Start recording before marking an incident.')
        if not isinstance(label, str) or len(label) > 160:
            raise ValueError('Incident label must be at most 160 characters.')
        self.submit({'capture_id': self.capture_id, 'id': uuid.uuid4().hex, 'name': safe_text(label),
                     'kind': 'evidence', 'duration_ms': 0, 'source': 'operator',
                     'clock': 'host-monotonic', 'start_ms': time.perf_counter_ns()/1e6,
                     'incident': True, 'details': {}})

    def _collect(self):
        while not self._closed.wait(.1):
            try:
                self.drain()
                if self.recording and self.deadline and time.monotonic() >= self.deadline:
                    self.stop('duration_limit')
            except Exception as exc:
                self.storage_error = type(exc).__name__ + ': ' + str(exc)
                self.stop('recorder_error')
        try:
            while self.queue:
                self.drain()
            with self.control_lock:
                self._checkpoint(force=True)
        except Exception as exc:
            self.storage_error = str(exc)

    def drain(self):
        # Only collector/test code calls this. The reader lock never touches producers.
        with self.control_lock:
            with self.queue_lock:
                batch = [self.queue.popleft() for _ in range(min(len(self.queue), 2048))]
            now = time.time()
            triggered = []
            with self.data_lock:
                for event in batch:
                    event['collected_at'] = now
                    self.received += 1
                    duration = event['duration_ms']
                    if event['kind'] != 'evidence' and not add_timing(self.operations, event):
                        self.dropped += 1
                    fast_lock = (event['kind'] == 'span' and '.lock' in event['name'] or
                                 event['kind'] == 'span' and '_lock.' in event['name']) and duration < FAST_LOCK_MS
                    if fast_lock:
                        self.fast_locks_aggregated += 1
                        continue
                    if len(self.events) == RECORD_LIMIT:
                        self.expired += 1
                    self.events.append(event)
                    # Ages are not work. Avoid continuously triggering on ordinary feedback age.
                    threshold = (1000 if 'feedback_age' in event['name'] else
                                 500 if event['name'].endswith(('receive_gap', 'source_gap', 'feedback_gap')) else 250)
                    slow = duration >= threshold and not event.get('hidden')
                    incident_key = (event['name'], event.get('side'))
                    explicit = event.get('incident') and (event['source'] == 'operator' or
                        now-self.last_explicit_incident.get(incident_key, 0) >= 5)
                    if explicit or slow and now-self.last_auto_incident >= 15:
                        if len(self.last_explicit_incident) >= 256:
                            self.last_explicit_incident.clear()
                        if explicit:
                            self.last_explicit_incident[incident_key] = now
                        if len(self.incidents) == self.incidents.maxlen:
                            self.incidents_evicted += 1
                        item = {'id': event['id'], 'at': now, 'name': event['name'],
                                'duration_ms': duration if event['kind'] != 'evidence' else None,
                                'trace_id': event.get('trace_id'), 'source': event['source'],
                                'details': event.get('details'), 'window_start': now-PRE_INCIDENT_S,
                                'window_end': now+POST_INCIDENT_S}
                        self.incidents.append(item); triggered.append(item)
                        self.detail_until = max(self.detail_until, now+POST_INCIDENT_S)
                        if slow:
                            self.last_auto_incident = now
                while self.events and now - self.events[0]['collected_at'] > WINDOW_S:
                    self.events.popleft(); self.expired += 1
                candidates = [e for e in self.events if now-PRE_INCIDENT_S <= e['collected_at'] <= self.detail_until]
            if not self.storage_error and (triggered or now <= self.detail_until):
                self._write_details(candidates)
            self._checkpoint()

    def _write_details(self, candidates):
        rows = []
        size = 0
        for event in candidates:
            if event['id'] in self.saved_ids:
                continue
            encoded = json.dumps(event, separators=(',', ':'), allow_nan=False) + '\n'
            length = len(encoded.encode())
            if self.detail_truncated or self.written + size + length > FILE_LIMIT:
                self.detail_truncated = True
                self.detail_omitted += 1
            else:
                rows.append(encoded); size += length
            self.saved_ids.add(event['id']); self.saved_order.append(event['id'])
        while len(self.saved_order) > RECORD_LIMIT * 2:
            self.saved_ids.discard(self.saved_order.popleft())
        if rows:
            started = time.perf_counter()
            with self.path.open('a') as handle:
                handle.write(''.join(rows))
            self.written += size
            self.writer_ms = (time.perf_counter()-started)*1000

    def _checkpoint(self, *, force=False):
        if not self.summary_path:
            return
        if self.storage_error and not force:
            return
        with self.data_lock:
            signature = (self.received, self.revision, self.dropped, self.detail_truncated,
                         tuple((p['source'], p['recording'], p['dropped']) for p in self.participants.values()))
        if not force and (not self.recording and signature == self.checkpoint_signature or
                          self.recording and time.monotonic()-self.last_checkpoint < CHECKPOINT_S):
            return
        value = self.snapshot()
        value.pop('events', None)
        with self.data_lock:
            value['statistics'] = list(self.operations.values())
            encoded = json.dumps(value, separators=(',', ':'), allow_nan=False)
        temporary = self.summary_path.with_suffix('.tmp')
        temporary.write_text(encoded, encoding='utf-8')
        temporary.replace(self.summary_path)
        self.summary_bytes = len(encoded.encode())
        self.last_checkpoint = time.monotonic()
        self.checkpoint_signature = signature

    def _restore(self):
        paths = sorted(self.directory.glob('*.summary.json'), key=lambda p: p.stat().st_mtime)
        if not paths:
            return
        path = paths[-1]
        try:
            if path.stat().st_size > 16*1024*1024:
                raise ValueError('Saved summary exceeds its limit')
            value = json.loads(path.read_text())
            capture = value['capture_id']
            if not re.fullmatch(r'[a-f0-9]{32}', capture) or path.name != capture+'.summary.json':
                raise ValueError('Invalid saved capture')
            self.path = self.directory / (capture+'.jsonl')
            if not self.path.is_file():
                raise ValueError('Saved detail file missing')
            self.capture_id, self.summary_path = capture, path
            self.side, self.started_at = value['side'], value['started_at']
            self.stopped_mono = time.monotonic()
            self.started_mono = self.stopped_mono-value['elapsed_s']
            self.revision = value['revision']+1
            self.stop_reason = 'interrupted' if value['recording'] else value.get('stop_reason')
            self.operations = {(op['source'], op['name'], op['side']): op for op in value['statistics']}
            self.incidents.extend(value.get('incidents', []))
            self.received, self.dropped = value['received'], value['host_dropped']
            self.participants = {p['source']: p for p in value.get('participants', [])}
            self.written = self.path.stat().st_size
            self.summary_bytes = path.stat().st_size
            for key in ('detail_truncated', 'detail_omitted', 'fast_locks_aggregated', 'incidents_evicted', 'observer_errors'):
                setattr(self, key, value.get(key, 0))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self.storage_error = 'Could not restore capture: '+str(exc)

    def incident_records(self, selected):
        """Read historical detail outside the producer/data locks, only on selection."""
        with self.control_lock:
            if not self.path:
                return []
            handle = self.path.open()
        records = []
        with handle:
            for line in handle:
                try:
                    event = json.loads(line)
                except ValueError:
                    continue  # A concurrent append or crash can leave a partial last line.
                if selected['window_start'] <= event.get('collected_at', 0) <= selected['window_end']:
                    records.append(event)
                    if len(records) > RECORD_LIMIT:
                        records = self._display_records(records)
        return records

    @staticmethod
    def _display_records(records):
        evidence = [e for e in records if e['kind'] == 'evidence'][-60:]
        return evidence + sorted((e for e in records if e['kind'] != 'evidence'),
                                 key=lambda e: e['duration_ms'], reverse=True)[:300-len(evidence)]

    def snapshot(self, *, incident=None):
        with self.data_lock:
            operations = [operation_summary(op) for op in self.operations.values()]
            records = list(self.events)
            selected = None
            if incident:
                selected = next((i for i in self.incidents if i['id'] == incident), None)
                records = [e for e in records if selected and selected['at'] - 10 <= e['collected_at'] <= selected['at'] + 5]
            dropped = self.dropped + sum(p['dropped'] for p in self.participants.values())
            warnings = []
            if self.detail_truncated:
                warnings.append('Detailed trace storage is full. Timing summaries continue while recording is on; later incident details are incomplete.')
            if dropped:
                warnings.append(f'{dropped} timing records were dropped. Counts and detailed traces have gaps.')
            if self.stop_reason and self.stop_reason != 'operator':
                warnings.append('Recording stopped automatically ('+self.stop_reason+'). Events after the stop are not captured.')
            if self.storage_error:
                warnings.append(self.storage_error)
            if self.observer_errors:
                warnings.append(f'{self.observer_errors} diagnostic observer errors occurred.')
            if self.incidents_evicted:
                warnings.append(f'{self.incidents_evicted} older incident entries are outside the bounded incident list; saved details remain in the export.')
            value = {**config(), 'status': 'recording' if self.recording else 'stopping' if self.queue else 'off',
                    'side': self.side, 'started_at': self.started_at, 'elapsed_s': max(0, (self.stopped_mono or time.monotonic())-self.started_mono) if self.capture_id else 0,
                    'remaining_s': max(0, self.deadline-time.monotonic()) if self.recording and self.deadline else None,
                    'stop_reason': self.stop_reason, 'storage_error': self.storage_error, 'observer_errors': self.observer_errors,
                    'warnings': warnings, 'detail_truncated': self.detail_truncated, 'detail_omitted': self.detail_omitted,
                    'fast_locks_aggregated': self.fast_locks_aggregated, 'incidents_evicted': self.incidents_evicted,
                    'summary_bytes': self.summary_bytes, 'summary_scope': 'whole_capture',
                    'coverage_updates_skipped': self.coverage_dropped,
                    'received': self.received, 'dropped': dropped,
                    'host_dropped': self.dropped, 'expired': self.expired,
                    'buffered': len(self.queue), 'retained': len(self.events), 'bytes_written': self.written,
                    'limits': {'queue': QUEUE_LIMIT, 'records': RECORD_LIMIT, 'window_s': WINDOW_S, 'file_bytes': FILE_LIMIT},
                    'writer_ms': getattr(self, 'writer_ms', 0), 'operations': sorted(operations, key=lambda o: o['max_ms'], reverse=True),
                    'incidents': list(self.incidents), 'participants': list(self.participants.values()),
                    'coverage': 'Host hooks are passive. Workers report through existing IPC. Browsers acknowledge via timing batches. Gateway transport is measured separately when available.'}
        if selected:
            archived = self.incident_records(selected)
            records = list({e['id']: e for e in [*archived, *records]}.values())
        value['events'] = self._display_records(records)
        value['selected_incident'] = selected
        return value

    def close(self):
        self.stop('shutdown')
        self._closed.set()
        self._thread.join(2)


CLIENT_OPERATIONS = frozenset(('browser.parse', 'browser.apply', 'browser.receive_gap', 'browser.presentation_wait',
    'browser.frame_gap', 'browser.event_loop_lag', 'browser.long_task', 'browser.feedback_age',
    'browser.iframe_delivery', 'browser.status_request', 'browser.status_apply', 'browser.iframe_snapshot',
    'gateway.receive_gap', 'gateway.parse', 'gateway.queue'))


def install(directory):
    global _recorder
    if _recorder:
        _recorder.close()
    _recorder = Recorder(directory)
    return _recorder


def shutdown():
    global _recorder
    if _recorder:
        _recorder.close()
        _recorder = None
