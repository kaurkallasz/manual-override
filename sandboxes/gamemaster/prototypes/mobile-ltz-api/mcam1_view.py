"""Optional, read-only MCAM1 presentation through its published still contract."""
import math
import time


def snapshot(module, side):
    base = dict(contract='mobile.mcam1', version=1, status='unavailable')
    # Camera assignment: Green receives MCAM1; Purple is reserved for MCAM2.
    # TODO(MCAM2): add Purple's own still contract/projection and asset route.
    # Until then, never discover or substitute MCAM1 for Purple.
    if side != 'green':
        return ({**base, 'error':'MCAM1 is assigned to Green; Purple is waiting for MCAM2.'}, None)
    try:
        camera = module('mcam1')
        if camera is None or not callable(getattr(camera, 'still_snapshot', None)):
            raise ValueError('MCAM1 is disabled or unavailable')
        frame = camera.still_snapshot()
        if (not isinstance(frame, dict) or frame.get('contract') != 'hhh.camera.still'
                or type(frame.get('version')) is not int or frame['version'] != 1
                or frame.get('status') != 'ready'):
            raise ValueError('MCAM1 has no fresh video')
        now = time.time()
        stamp = frame.get('captured_at')
        if (type(stamp) not in (int, float) or not math.isfinite(stamp)
                or not -1 <= now - stamp <= 1.5):
            raise ValueError('MCAM1 video is stale')
        if any(type(frame.get(key)) is not int or not 1 <= frame[key] <= 4096 for key in ('width', 'height')):
            raise ValueError('MCAM1 dimensions unavailable')
        image = frame.get('image')
        if (frame.get('mime_type') != 'image/jpeg' or not isinstance(image, bytes)
                or not 4 <= len(image) <= 4 * 1024 * 1024
                or not image.startswith(b'\xff\xd8') or not image.endswith(b'\xff\xd9')):
            raise ValueError('MCAM1 frame unavailable')
        return ({**base, 'status':'ready', 'width':frame['width'], 'height':frame['height'],
                 'captured_at':stamp, 'server_time':now, 'max_age_s':1.5}, image)
    except Exception as exc:
        return ({**base, 'error':str(exc)}, None)
