"""Bounded, passive delivery measurements. Never reads game or robot state."""
from collections import deque
import copy
import json
import re
import threading
import time


WINDOW_S = 10.0
SAMPLE_INTERVAL_S = 1.0
MAX_PREVIEW_BYTES = 256 * 1024
SECRET_KEYS = {'password', 'token', 'secret', 'authorization', 'cookie', 'session',
               'access_token', 'refresh_token', 'service_token', 'bridge_secret', 'client_auth'}


def safe_value(value, depth=0):
    if depth > 16:
        return '[depth limit]'
    if isinstance(value, dict):
        return {str(key): '[redacted]' if str(key).lower() in SECRET_KEYS
                or str(key).lower().endswith(('_token', '_secret', '_password'))
                else safe_value(item, depth + 1) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [safe_value(item, depth + 1) for item in value[:2000]] + (
            ['[remaining items omitted]'] if len(value) > 2000 else [])
    if isinstance(value, str):
        value = re.sub(r'(?i)([?&](?:token|key|auth|session|secret)=)[^&#\s]+', r'\1[redacted]', value)
        value = re.sub(r'(?i)\b(?:Bearer\s+\S+|(?:password|token|secret|authorization|cookie|session)\s*[:=]\s*\S+)', '[redacted]', value)
        return value[:4096] + ('…' if len(value) > 4096 else '')
    return value


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), default=str).encode('utf-8')


class DeliveryDiagnostics:
    def __init__(self):
        self.lock = threading.Lock()
        self.started_at = time.time()
        self.started_mono = time.monotonic()
        self.recent = deque(maxlen=60)
        self.teams = {}
        for side in ('green', 'purple'):
            self.teams[side] = {
                'generated': 0, 'generated_unavailable': 0, 'build_total_ms': 0.0,
                'build_max_ms': 0.0, 'build_last_ms': None, 'last_generated_at': None,
                'http_responses': 0, 'http_errors': 0, 'http_bytes': 0,
                'sse_frames': 0, 'sse_snapshots': 0, 'sse_updates': 0, 'sse_pings': 0,
                'sse_bytes': 0, 'active_streams': 0, 'opened_streams': 0,
                'closed_streams': 0, 'stream_errors': 0, 'last_emitted_at': None,
                'samples': {}, 'sample_deadlines': {}, 'traffic': deque(maxlen=4096),
            }

    def _sample(self, side, channel, value, *, kind, body_bytes=None, route=None):
        now = time.monotonic()
        with self.lock:
            team = self.teams[side]
            previous = team['samples'].get(channel)
            if now < team['sample_deadlines'].get(channel, 0) and previous and previous['kind'] == kind:
                return
            team['sample_deadlines'][channel] = now + SAMPLE_INTERVAL_S
        raw_bytes = len(encoded(value)) if body_bytes is None else body_bytes
        clean = safe_value(value)
        contents = clean.get('state', {}) if isinstance(clean, dict) and clean.get('contract') == 'hub.live' else clean
        fields = [{'name': key, 'bytes': len(encoded(item)),
                   'items': len(item) if isinstance(item, (list, dict)) else None}
                  for key, item in contents.items()] if isinstance(contents, dict) else []
        text = json.dumps(clean, ensure_ascii=False, indent=2, default=str).encode('utf-8')
        truncated = len(text) > MAX_PREVIEW_BYTES
        preview = text[:MAX_PREVIEW_BYTES].decode('utf-8', errors='ignore')
        if truncated:
            preview += '\n… preview truncated …'
        sample = {'captured_at': time.time(), 'kind': kind, 'route': route,
                  'body_bytes': raw_bytes, 'fields': sorted(fields, key=lambda x: -x['bytes']),
                  'preview': preview, 'truncated': truncated}
        with self.lock:
            # Do not replace a newer concurrent sample with an older result.
            if self.teams[side]['sample_deadlines'][channel] == now + SAMPLE_INTERVAL_S:
                self.teams[side]['samples'][channel] = sample

    def generated(self, side, value, build_ms):
        with self.lock:
            team = self.teams[side]
            team['generated'] += 1
            team['generated_unavailable'] += value.get('status') == 'unavailable'
            team['build_total_ms'] += build_ms
            team['build_max_ms'] = max(team['build_max_ms'], build_ms)
            team['build_last_ms'] = build_ms
            team['last_generated_at'] = time.time()
            team['traffic'].append((time.monotonic(), 'generated', 0))
        self._sample(side, 'generated', value, kind='state')

    def http_response(self, side, route, status, body_bytes, content_type, elapsed_ms, value=None, action=None):
        with self.lock:
            team = self.teams[side]
            team['http_responses'] += 1
            team['http_errors'] += status >= 400
            team['http_bytes'] += body_bytes
            team['traffic'].append((time.monotonic(), 'http', body_bytes))
            self.recent.appendleft({'at': time.time(), 'side': side, 'kind': 'http',
                                    'route': route, 'status': status, 'bytes': body_bytes,
                                    'duration_ms': round(elapsed_ms, 2), 'action': safe_value(action)})
        self._sample(side, 'http', value if value is not None else {'content_type': content_type},
                     kind='http', body_bytes=body_bytes, route=route)

    def stream_open(self, side):
        with self.lock:
            team = self.teams[side]
            team['active_streams'] += 1
            team['opened_streams'] += 1
            self.recent.appendleft({'at': time.time(), 'side': side, 'kind': 'stream_open'})

    def stream_close(self, side, failed=False):
        with self.lock:
            team = self.teams[side]
            team['active_streams'] = max(0, team['active_streams'] - 1)
            team['closed_streams'] += 1
            team['stream_errors'] += bool(failed)
            self.recent.appendleft({'at': time.time(), 'side': side,
                                    'kind': 'stream_error' if failed else 'stream_close'})

    def emitted(self, side, chunk):
        wire = chunk.encode('utf-8') if isinstance(chunk, str) else chunk
        kind = 'ping' if wire.startswith(b':') else 'update' if wire.startswith(b'event: update') else 'snapshot'
        now = time.monotonic()
        with self.lock:
            team = self.teams[side]
            team['sse_frames'] += 1
            team['sse_' + kind + 's'] += 1
            team['sse_bytes'] += len(wire)
            team['last_emitted_at'] = time.time()
            team['traffic'].append((now, 'sse' if kind != 'ping' else 'ping', len(wire)))
            sample = team['samples'].get('sse')
            capture = kind != 'ping' and (now >= team['sample_deadlines'].get('sse', 0)
                                         or not sample or sample['kind'] != kind)
        if capture:
            data = b'\n'.join(line[6:] for line in wire.splitlines() if line.startswith(b'data: '))
            self._sample(side, 'sse', json.loads(data), kind=kind, body_bytes=len(wire), route='/api/events')

    def snapshot(self, *, side=None, payloads=False, channel=None):
        now = time.monotonic()
        with self.lock:
            teams = {}
            for name, team in self.teams.items():
                if side is not None and name != side:
                    continue
                window = max(.001, min(WINDOW_S, now - self.started_mono))
                while team['traffic'] and team['traffic'][0][0] < now - WINDOW_S:
                    team['traffic'].popleft()
                traffic = list(team['traffic'])
                item = {k: v for k, v in team.items() if k not in ('traffic', 'samples', 'sample_deadlines', 'build_total_ms')}
                item['build_mean_ms'] = team['build_total_ms'] / team['generated'] if team['generated'] else None
                item['generated_hz'] = sum(kind == 'generated' for _, kind, _ in traffic) / window
                item['emitted_hz'] = sum(kind == 'sse' for _, kind, _ in traffic) / window
                item['emitted_bytes_per_s'] = sum(size for _, kind, size in traffic if kind in ('sse', 'ping')) / window
                item['http_bytes_per_s'] = sum(size for _, kind, size in traffic if kind == 'http') / window
                item['samples'] = {
                    name: copy.deepcopy(sample) if payloads and channel in (None, name) else
                    {k: v for k, v in sample.items() if k not in ('preview', 'fields')}
                    for name, sample in team['samples'].items()}
                teams[name] = item
            return {'contract': 'mobile.delivery-diagnostics', 'version': 1,
                    'started_at': self.started_at, 'sampled_at': time.time(), 'window_s': WINDOW_S,
                    'teams': teams, 'recent': [dict(row) for row in self.recent if side is None or row['side'] == side]}
