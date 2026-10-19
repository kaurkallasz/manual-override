"""Validation of Board's optional camera-only occupancy contract."""
import math
import time


def unavailable(error):
    return {'contract': 'photon.board.occupancy', 'version': 1,
            'status': 'unavailable', 'error': str(error)[:500], 'relations': []}


def validated(value, now=None):
    now = time.time() if now is None else now
    try:
        if (not isinstance(value, dict) or value.get('contract') != 'photon.board.occupancy'
                or type(value.get('version')) is not int or value['version'] != 1):
            raise ValueError('Board occupancy contract mismatch')
        if value.get('status') != 'ready':
            return unavailable(value.get('error') or 'Board occupancy unavailable')
        def number(n):
            return type(n) in (int, float) and math.isfinite(n)
        grace = value.get('policy', {}).get('grace_s', .35)
        if not number(grace) or not .35 <= grace <= .9:
            raise ValueError('Invalid occupancy dropout policy')
        stamp, frame = value.get('sampled_at'), value.get('frame_at')
        epoch, revision = value.get('source_epoch'), value.get('revision')
        relations = value.get('relations')
        if (not number(stamp) or not number(frame) or not -1 <= now - stamp <= 1.5
                or not -1 <= now - frame <= 1.5 or frame > stamp + .01
                or not isinstance(epoch, str) or not 1 <= len(epoch) <= 160
                or type(revision) is not int or revision < 0
                or not isinstance(relations, list) or len(relations) > 900):
            raise ValueError('Invalid or stale occupancy metadata')
        tags, markers, identities, clean = set(), set(), set(), []
        for rec in relations:
            if not isinstance(rec, dict):
                raise ValueError('Invalid occupancy relationship')
            tag, marker, identity = rec.get('movable_id'), rec.get('marker_id'), rec.get('relation_id')
            state = rec.get('state')
            since, evidence, departure = rec.get('observed_since'), rec.get('evidence_at'), rec.get('departed_at')
            if (type(tag) is not int or not 100 <= tag <= 999 or tag in tags
                    or type(marker) is not int or not 0 <= marker < 100
                    or not isinstance(identity, str) or not 1 <= len(identity) <= 240 or identity in identities
                    or state not in ('present', 'departed', 'unavailable')
                    or not number(since) or not number(evidence) or since > evidence or evidence > frame + .01
                    or departure is not None and (not number(departure) or departure > evidence)
                    or state == 'departed' and departure is None
                    or state == 'present' and marker in markers):
                raise ValueError('Invalid or conflicting occupancy relationship')
            if state == 'present' and evidence - since < .55 - 1e-6:
                raise ValueError('Occupancy acquired before dwell completed')
            tags.add(tag)
            identities.add(identity)
            if state == 'present':
                markers.add(marker)
            clean.append({key: rec[key] for key in ('movable_id', 'marker_id', 'relation_id',
                         'state', 'observed_since', 'evidence_at', 'departed_at')})
            if state == 'present' and now - evidence > grace:
                clean[-1]['state'] = 'unavailable'
        return {'contract': 'photon.board.occupancy', 'version': 1,
                'status': 'ready', 'error': None, 'sampled_at': stamp,
                'frame_at': frame, 'source_epoch': epoch, 'revision': revision,
                'relations': clean}
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError) as exc:
        return unavailable(exc)
