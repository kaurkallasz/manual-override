"""Bounded diagnostic values and full-capture timing statistics; no I/O."""
import math
import re


def safe_text(value):
    if not isinstance(value, str):
        return None
    value = re.sub(r'https?://\S+', '[url]', value)
    value = re.sub(r'(?i)\b(?:password|token|authorization|cookie|session)\s*[:=]\s*\S+', '[credential]', value)
    return ' '.join(value.split())[:240]


def clean(value):
    """Only board decisions and driver health, never raw state or commands."""
    if not isinstance(value, dict):
        return {}
    out = {}
    for key in ('status', 'error', 'reason', 'phase', 'motion_invalidation', 'servo_error',
                'driver_error', 'error_kind', 'operation', 'mapping_gate', 'mapping_source'):
        if key in value:
            out[key] = safe_text(value[key])
    for key in ('epoch', 'frame_at', 'observed_at', 'area', 'max_ratio', 'minimum_px', 'maximum_px',
                'pid', 'exitcode', 'heartbeat_age_ms', 'tag_id', 'queue_index', 'motion_epoch',
                'feedback_age_ms', 'feedback_status_age_ms', 'feedback_game_delta_ms', 'status_request_ms',
                'source_gap_ms', 'build_ms', 'delivery_sequence',
                'frame_age_ms', 'sampler_age_ms', 'poll_age_ms'):
        n = value.get(key)
        if type(n) in (int, float) and math.isfinite(n) and abs(n) < 1e12:
            out[key] = n
    for key in ('alive', 'connected', 'enabled', 'feedback_ok', 'motion_ready'):
        if type(value.get(key)) is bool:
            out[key] = value[key]
    if isinstance(value.get('run_id'), str) and re.fullmatch(r'[a-f0-9]{32}', value['run_id']):
        out['run_id'] = value['run_id']
    if isinstance(value.get('epoch'), str) and re.fullmatch(r'[a-f0-9]{32}', value['epoch']):
        out['epoch'] = value['epoch']
    for key in ('anchor_ids', 'pending_fixed_ids', 'blocked_fixed_ids', 'board_motion_ids', 'accepted_ids', 'visible_ids'):
        if isinstance(value.get(key), list):
            out[key] = [n for n in value[key][:64] if type(n) is int and 0 <= n <= 1023]
    if isinstance(value.get('hull'), list):
        out['hull'] = [list(p) for p in value['hull'][:30] if isinstance(p, (list, tuple)) and len(p) == 2
                       and all(type(n) in (int, float) and math.isfinite(n) and 0 <= n <= 1 for n in p)]
    for key in ('quarantined_tags', 'rejected'):
        if isinstance(value.get(key), list):
            out[key] = []
            for item in value[key][:64]:
                if isinstance(item, dict) and type(item.get('id')) is int and 0 <= item['id'] <= 1023:
                    row = {'id': item['id'], 'reason': safe_text(item.get('reason'))}
                    size = item.get('size_px')
                    if type(size) in (int, float) and math.isfinite(size) and 0 <= size <= 100000:
                        row['size_px'] = size
                    out[key].append(row)
    for key in ('verification', 'size_filter', 'board', 'driver'):
        if isinstance(value.get(key), dict):
            # Explicit depth bound even for untrusted browser dictionaries.
            child = {k: v for k, v in value[key].items() if k not in ('board', 'driver')}
            if key in ('verification', 'size_filter'):
                child = {k: v for k, v in child.items() if k not in ('verification', 'size_filter')}
            out[key] = clean(child)
    return out


def add_timing(operations, event):
    key = (event['source'], event['name'], event.get('side'))
    if key not in operations and len(operations) >= 1024:
        return False
    op = operations.setdefault(key, dict(source=key[0], name=key[1], side=key[2], kind=event['kind'],
        count=0, total_ms=0, max_ms=0, cpu_ms=0, self_ms=0, histogram={}))
    duration = event['duration_ms']
    # Upper bounds with 5% relative resolution, starting at 0.01 ms.
    bucket = min(400, max(0, math.ceil(math.log1p(duration / .01) / math.log(1.05))))
    op['histogram'][str(bucket)] = op['histogram'].get(str(bucket), 0) + 1
    op['count'] += 1
    op['total_ms'] += duration
    op['max_ms'] = max(op['max_ms'], duration)
    op['cpu_ms'] += event.get('cpu_ms') or 0
    op['self_ms'] += event.get('self_ms') or 0
    return True


def operation_summary(op):
    out = {k: v for k, v in op.items() if k != 'histogram'}
    cumulative = 0
    for bucket, count in sorted(op['histogram'].items(), key=lambda p: int(p[0])):
        cumulative += count
        for name, percentile in (('p50_ms', .5), ('p95_ms', .95), ('p99_ms', .99)):
            if name not in out and cumulative >= math.ceil(op['count'] * percentile):
                out[name] = min(op['max_ms'], .01 * (1.05 ** int(bucket) - 1))
    return out | {'percentile_samples': op['count'], 'percentile_method': 'whole-capture-5%-histogram'}
