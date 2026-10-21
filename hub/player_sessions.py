"""Hub-owned browser identities, revocation, presence and reset admission state."""
import json
import os
from pathlib import Path
import re
import secrets
import threading
import time
from .live import LiveState

TEAMS = ('green', 'purple')


def operation_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_:.-]{1,160}', value):
        raise ValueError('A valid operation ID is required.')
    return value


class PlayerSessions:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.RLock()
        self.transition = threading.Lock()
        self.live = LiveState()
        self.rows = {}
        self.state = {'pending': None, 'completed': []}
        if self.path.exists():
            try:
                value = json.loads(self.path.read_text())
                if (not isinstance(value, dict) or not isinstance(value.get('completed'), list)
                        or 'pending' not in value or value['pending'] is not None
                        and (not isinstance(value['pending'], dict) or not isinstance(value['pending'].get('id'), str))):
                    raise ValueError('Invalid player access recovery file')
                self.state = value
            except Exception:
                # A damaged recovery record must never reopen robot access.
                self.state['pending'] = {'id': 'recovery', 'context': None,
                                         'error': 'Player access recovery file was unreadable. Retry Clean reset to recover safely.'}

    @property
    def blocked(self):
        with self.lock:
            return self.state['pending'] is not None

    def _save(self, value):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w') as handle:
            json.dump(value, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self.path)
        descriptor = os.open(self.path.parent, os.O_RDONLY)
        try: os.fsync(descriptor)
        finally: os.close(descriptor)
        self.state = value

    def create(self, team, ip):
        with self.lock:
            if self.blocked:
                raise ValueError('Clean reset in progress. Wait for the new QR codes.')
            if team not in TEAMS:
                raise ValueError('Unknown player team')
            now = time.time()
            self.rows = {key: row for key, row in self.rows.items() if now-row['created_at'] < 14*86400}
            if len(self.rows) >= 4096:
                raise ValueError('Player session limit reached.')
            sid = secrets.token_urlsafe(24)
            self.rows[sid] = dict(id=sid, team=team, ip=ip or 'Unavailable', created_at=now,
                                  last_seen=now, revoked=False, request_lock=threading.RLock())
        self.live.bump()
        return sid

    def active(self, sid, team=None):
        with self.lock:
            row = self.rows.get(sid) if isinstance(sid, str) else None
            return bool(not self.blocked and row and not row['revoked']
                        and time.time()-row['created_at'] < 14*86400
                        and (team is None or row['team'] == team))

    def touch(self, sid, ip=None):
        with self.lock:
            row = self.rows.get(sid)
            if not row or not self.active(sid) or time.time()-row['last_seen'] < 2:
                return
            row['last_seen'] = time.time()
            if ip: row['ip'] = ip
        self.live.bump()

    def request_lock(self, sid):
        with self.lock:
            return self.rows[sid]['request_lock']

    def revoke(self, sid):
        with self.lock:
            if sid not in self.rows: raise ValueError('Player session no longer exists.')
            self.rows[sid]['revoked'] = True
        self.live.bump()

    def drain(self, sid=None):
        with self.lock:
            rows = [self.rows[sid]] if sid else list(self.rows.values())
        for row in rows:
            lock = row['request_lock']
            if not lock.acquire(timeout=15):
                raise ValueError('Waiting for an earlier player command to finish. Retry.')
            lock.release()

    def snapshot(self, names=None, controlling=()):
        with self.lock:
            rows = []
            for row in self.rows.values():
                if not row['revoked'] and (names or {}).get(row['team']):
                    row['player_name'] = names[row['team']]
                visible = {k: v for k, v in row.items() if k != 'request_lock'}
                visible['player_name'] = row.get('player_name') or 'No player selected'
                visible['status'] = ('session ended' if row['revoked'] else
                    'disconnected' if time.time()-row['last_seen'] > 20 else
                    'controlling' if row['id'] in controlling else 'viewing')
                rows.append(visible)
            return dict(contract='hub.player-sessions', version=1, rows=rows,
                        reset=json.loads(json.dumps(self.state['pending'])), blocked=self.blocked,
                        generation=self.state['completed'][-1] if self.state['completed'] else None)

    def begin_reset(self, operation, context):
        operation_id(operation)
        with self.lock:
            if operation in self.state['completed']: return False
            pending = self.state['pending']
            if pending and pending['id'] != operation:
                raise ValueError('A clean reset is pending. Retry that reset first.')
            if not pending:
                self._save({**self.state, 'pending': {'id': operation, 'context': context, 'error': None}})
            for row in self.rows.values(): row['revoked'] = True
        self.live.bump()
        return True

    def reset_failed(self, error):
        with self.lock:
            self._save({**self.state, 'pending': {**self.state['pending'], 'error': str(error)}})
        self.live.bump()

    def finish_reset(self, operation):
        with self.lock:
            if not self.state['pending'] or self.state['pending']['id'] != operation:
                raise ValueError('Clean reset identity changed')
            self._save({'pending': None, 'completed': self.state['completed']+[operation]})
        self.live.bump()
