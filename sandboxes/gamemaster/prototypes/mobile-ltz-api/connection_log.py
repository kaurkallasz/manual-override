"""Bounded, credential-free connection evidence owned by Mobile LTZ API."""
from collections import OrderedDict, deque
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import threading
import time
from shared import delay_trace as trace
from shared.delay_evidence import clean as clean_evidence

LOG_PATH = Path(__file__).with_name('data') / 'connection-events.jsonl'
MAX_BYTES = 2 * 1024 * 1024
BACKUPS = 2
_lock = threading.Lock()
_seen = OrderedDict()
_rates = {'green': deque(), 'purple': deque()}
_names = re.compile(r'^[a-z][a-z0-9_.-]{0,63}$')
_ids = re.compile(r'^[a-zA-Z0-9_-]{1,80}$')
_numbers = {'game_age_ms', 'controller_game_age_ms', 'controller_age_ms', 'feedback_age_ms', 'parent_age_ms',
            'robot_age_ms', 'motion_epoch', 'previous_motion_epoch', 'robot_mode',
            'source_gap_ms', 'receive_gap_ms', 'build_ms', 'delivery_sequence', 'pending_commands',
            'tag_id', 'queue_index', 'detection_age_ms', 'calibration_revision',
            'placement_offset_mm', 'tuning_offset_mm'}
_flags = {'hidden', 'focused', 'online', 'connected', 'enabled', 'feedback_ok',
          'motion_ready', 'feed_ready', 'paused', 'virtual', 'connection_ready',
          'calibration_loading', 'view_active', 'had_session'}
_labels = {'phase', 'journey_phase', 'control_mode', 'status', 'action', 'code', 'safety_status', 'calibration_layer', 'motion_invalidation'}


def _text(value):
    if not isinstance(value, str):
        return None
    # Errors may contain URLs or opaque credentials; neither belongs in this log.
    value = re.sub(r'https?://\S+', '[url]', value)
    value = re.sub(r'(?i)\b(?:password|token|authorization|cookie|session)\s*[:=]\s*\S+', '[credential]', value)
    value = re.sub(r'(?i)\b[a-f0-9]{32,}\b', '[id]', value)
    return ' '.join(value.split())[:240]


def clean_event(data):
    if not isinstance(data, dict) or type(data.get('version')) is not int or data['version'] != 1:
        raise ValueError('Connection diagnostic v1 required.')
    if not isinstance(data.get('id'), str) or not _ids.fullmatch(data['id']):
        raise ValueError('Invalid diagnostic id.')
    for key in ('source', 'event'):
        if not isinstance(data.get(key), str) or not _names.fullmatch(data[key]):
            raise ValueError('Invalid diagnostic '+key+'.')
    at = data.get('client_at')
    if type(at) not in (float, int) or not math.isfinite(at) or not 0 <= at < 1e11:
        raise ValueError('Invalid diagnostic time.')
    result = {k: data[k] for k in ('id', 'source', 'event', 'client_at')}
    result['reason'] = _text(data.get('reason'))
    context = data.get('context', {})
    if not isinstance(context, dict):
        raise ValueError('Invalid diagnostic context.')
    safe = {}
    for key, value in context.items():
        if key in _numbers and type(value) in (int, float) and math.isfinite(value) and abs(value) <= 1e12:
            safe[key] = round(value, 2)
        elif key in _flags and type(value) is bool:
            safe[key] = value
        elif key in _labels and isinstance(value, str) and _names.fullmatch(value):
            safe[key] = value
        elif key in ('run_id', 'build', 'page_id') and isinstance(value, str) and re.fullmatch(r'[a-f0-9]{32}', value):
            safe[key] = value
        elif key in ('game_error', 'robot_error'):
            safe[key] = _text(value)
        elif trace.enabled() and key == 'mapping_gate' and isinstance(value, str) and _names.fullmatch(value):
            safe[key] = value
        elif trace.enabled() and key == 'servo_error':
            safe[key] = _text(value)
        elif trace.enabled() and key == 'board' and isinstance(value, dict):
            safe[key] = clean_evidence(value)
    result['context'] = safe
    return result


def append(side, data):
    event = clean_event(data)
    now = time.time()
    event.update(contract='mobile.connection-event', version=1, side=side, received_at=now,
                 received_utc=datetime.fromtimestamp(now, timezone.utc).isoformat())
    with _lock:
        key = (side, event['id'])
        if key in _seen:
            return True
        rate = _rates[side]
        while rate and rate[0] < time.monotonic()-60:
            rate.popleft()
        if len(rate) >= 240:
            return False
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        if LOG_PATH.exists() and LOG_PATH.stat().st_size >= MAX_BYTES:
            for i in range(BACKUPS, 0, -1):
                source = Path(str(LOG_PATH)+'.'+str(i-1)) if i > 1 else LOG_PATH
                if source.exists():
                    source.replace(str(LOG_PATH)+'.'+str(i))
        with LOG_PATH.open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(event, ensure_ascii=False, allow_nan=False, separators=(',', ':'))+'\n')
        rate.append(time.monotonic())
        _seen[key] = True
        while len(_seen) > 4096:
            _seen.popitem(last=False)
    if trace.enabled():
        trigger = event['event'] in {'cue_motion_held', 'cue_command_failed', 'command_failed',
            'motion_epoch_changed', 'robot_disconnected', 'feedback_stale', 'motion_not_ready', 'suspend'}
        trace.evidence('connection.'+event['event'], {**event['context'], 'reason': event['reason']},
                       side=side, incident=trigger)
    return True


def export():
    with _lock:
        paths = [Path(str(LOG_PATH)+'.'+str(i)) for i in range(BACKUPS, 0, -1)] + [LOG_PATH]
        return b''.join(path.read_bytes() for path in paths if path.exists())
