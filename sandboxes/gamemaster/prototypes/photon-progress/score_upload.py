"""Module-owned scoreboard outbox and upload-only installation pairing."""
import hashlib
import json
import os
import re
import secrets
import ssl
import sys
from pathlib import Path
import threading
import time
import urllib.error
import urllib.request

BASE_URL = 'https://mecharena.eu/score/api.php'


def normalize_email(value):
    if value is None or value == '':
        return None
    if not isinstance(value, str):
        raise ValueError('Enter a valid email address or leave it blank')
    value = value.strip().lower()
    if (len(value) > 254 or not re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,63}", value)
            or '..' in value or value.startswith('.') or '.@' in value):
        raise ValueError('Enter a valid email address or leave it blank')
    return value


def normalize_emails(value):
    """Canonical private contact list; pairing contacts still use normalize_email."""
    if value is None or isinstance(value, str) and not value.strip():
        return []
    if not isinstance(value, str) or len(value) > 2600:
        raise ValueError('Enter up to 10 email addresses separated by commas')
    parts = value.split(',')
    if len(parts) > 20 or any(not part.strip() for part in parts):
        raise ValueError('Separate complete email addresses with commas')
    emails = sorted({normalize_email(part) for part in parts})
    if len(emails) > 10:
        raise ValueError('Use no more than 10 email addresses per profile')
    return emails


def initialize(db):
    db.execute('CREATE TABLE IF NOT EXISTS score_contacts(player_id TEXT PRIMARY KEY REFERENCES players(id), email TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS score_exported(run_id TEXT PRIMARY KEY)')
    db.execute('CREATE TABLE IF NOT EXISTS score_outbox(id TEXT PRIMARY KEY, payload TEXT NOT NULL, tries INTEGER NOT NULL DEFAULT 0, next_at REAL NOT NULL DEFAULT 0, error TEXT)')


def queue(db, key, payload):
    body = json.dumps(payload, separators=(',', ':'), allow_nan=False)
    if len(body.encode()) > 2000000:
        raise ValueError('Scoreboard result exceeds the 2 MB upload limit')
    db.execute('INSERT OR IGNORE INTO score_outbox(id,payload) VALUES(?,?)', (key, body))


class ScoreContacts:
    def score_add_contact(self, db, player, email):
        emails = normalize_emails(email)
        if not emails:
            return
        previous = db.execute('SELECT email FROM score_contacts WHERE player_id=?', (player['id'],)).fetchone()
        if previous:
            existing = set(normalize_emails(previous[0]))
            if not existing.issubset(emails):
                raise ValueError('This profile already has scoreboard emails. Include all existing addresses when adding teammates; addresses cannot be replaced.')
            if existing == set(emails):
                return
        canonical = ','.join(emails)
        db.execute('INSERT INTO score_contacts VALUES(?,?) ON CONFLICT(player_id) DO UPDATE SET email=excluded.email', (player['id'], canonical))
        payload = json.dumps({'kind': 'profile', 'player_id': player['id'], 'email': canonical,
                             'name': player['name'], 'event_id': player['event_id']}, separators=(',', ':'))
        # Keep its queue position. A concurrent upload deletes only the exact
        # acknowledged payload, so adding teammates cannot lose the newer list.
        db.execute('INSERT INTO score_outbox(id,payload) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,tries=0,next_at=0,error=NULL',
                   ('profile:' + player['id'], payload))

    def score_set_contact(self, side, email, event_id):
        email = ','.join(normalize_emails(email))
        if not email:
            raise ValueError('Enter at least one email address')
        with self.transaction(write=True) as db:
            row = db.execute('SELECT player_id FROM sessions WHERE side=?', (side,)).fetchone()
            if not row:
                raise ValueError('Select a player first')
            player = self._player(db, row[0])
            if player['event_id'] != event_id:
                raise ValueError('Event changed; refresh this player')
            self.score_add_contact(db, player, email)
            # Existing local history is shared only with the registered mailboxes.
            for row in db.execute('SELECT a.data FROM attempts a JOIN participants p ON a.id=p.run_id WHERE p.player_id=?', (player['id'],)):
                self.score_queue_result(db, json.loads(row[0]))
            self._touch(db)

    def score_contact_status(self, db, player_id):
        row = db.execute('SELECT email FROM score_contacts WHERE player_id=?', (player_id,)).fetchone() if player_id else None
        pending = db.execute('SELECT tries FROM score_outbox WHERE id=?', ('profile:' + player_id,)).fetchone() if row else None
        state = ('retrying' if pending['tries'] else 'queued') if pending else 'submitted' if row else 'not_added'
        count = len(normalize_emails(row[0])) if row else 0
        messages = {
            'not_added': 'Add email addresses to receive your game statistics. Separate teammates with commas.',
            'queued': 'Email addresses saved on this game. Waiting to upload before sending each person a sign-in email.',
            'retrying': 'Your email addresses are saved. Sending is delayed; the game will retry automatically. Ask the operator if this continues.',
            'submitted': 'Your profile is online and sign-in emails have been submitted for delivery. Check each inbox or spam, or request a fresh link on the scoreboard.',
        }
        return {'email_added': bool(row), 'email_count': count, 'upload_state': state,
                'message': messages[state], 'url': 'https://mecharena.eu/score'}

    def score_queue_result(self, db, attempt):
        # A synthetic interruption can still be replaced by the pending final
        # result after restart. Never publish that provisional record.
        if attempt['outcome'] not in ('won', 'overrun', 'operator_ended', 'aborted'):
            return
        if db.execute('SELECT 1 FROM score_exported WHERE run_id=?', (attempt['run_id'],)).fetchone():
            return
        ids = [p['player_id'] for p in attempt['participants']]
        if not any(db.execute('SELECT 1 FROM score_contacts WHERE player_id=?', (pid,)).fetchone() for pid in ids):
            return
        event = json.loads(db.execute('SELECT data FROM game_events WHERE id=?', (attempt['event_id'],)).fetchone()[0])
        queue(db, 'result:' + attempt['run_id'], {'kind': 'result', 'run_id': attempt['run_id'],
              'event_id': attempt['event_id'], 'event_name': event['name'],
              'finished_at': attempt['finished_at'], 'player_ids': ids,
              'receipts': {pid: self.receipt_for_attempt(db, attempt, pid) for pid in ids}})
        db.execute('INSERT INTO score_exported VALUES(?)', (attempt['run_id'],))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Scoreboard redirect rejected')


class UploadClient:
    def __init__(self, store, directory, on_change=lambda: None, transport=None):
        self.store, self.directory, self.on_change = store, directory, on_change
        self.path = directory / 'installation.json'
        self.stop_event = threading.Event()
        self.wake = threading.Event()
        self.lock = threading.RLock()
        self.thread = None
        self.transport = transport or self.request
        self.error = None
        self.paired = False
        self.pair_next = 0

    def read_config(self):
        if not self.path.exists():
            self.paired = False
            return {}
        value = json.loads(self.path.read_text())
        if not isinstance(value, dict) or not re.fullmatch(r'[a-f0-9]{64}', value.get('upload_key', '')):
            raise ValueError('Invalid installation configuration')
        self.paired = bool(value.get('installation_id'))
        return value

    def save_config(self, value):
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        temp = self.path.with_suffix('.tmp')
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as f:
            json.dump(value, f); f.flush(); os.fsync(f.fileno())
        os.replace(temp, self.path)
        os.chmod(self.path, 0o600)
        self.paired = bool(value.get('installation_id'))

    def request(self, action, payload, key=None):
        body = json.dumps(payload, separators=(',', ':'), allow_nan=False).encode()
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        if key:
            headers['Authorization'] = 'Bearer ' + key
        req = urllib.request.Request(BASE_URL + '?action=' + action, body, headers, method='POST')
        try:
            context = ssl.create_default_context()
            # python.org macOS installations can lack their optional CA bundle.
            # Use the OS bundle in that case; certificate and hostname checks stay on.
            if not context.get_ca_certs() and sys.platform == 'darwin' and Path('/etc/ssl/cert.pem').is_file():
                context.load_verify_locations(cafile='/etc/ssl/cert.pem')
            with urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=context)).open(req, timeout=15) as response:
                value = json.loads(response.read(65537))
        except urllib.error.HTTPError as exc:
            # Never include request headers, response bodies or secrets in logs.
            if exc.code in (401, 403):
                raise ValueError('Installation access rejected; check pairing or revocation') from None
            raise ValueError('Scoreboard returned HTTP ' + str(exc.code)) from None
        if not isinstance(value, dict) or value.get('ok') is not True:
            raise ValueError('Invalid scoreboard acknowledgement')
        return value

    def request_pairing(self, name, contact_email):
        if (not isinstance(name, str) or not 1 <= len(name.strip().encode()) <= 80
                or re.search(r'[\x00-\x1f\x7f]', name)):
            raise ValueError('Enter an installation name (1–80 bytes, no control characters)')
        email = normalize_email(contact_email)
        if not email:
            raise ValueError('Enter an operator contact email')
        with self.lock:
            cfg = self.read_config()
            if cfg.get('installation_id'):
                raise ValueError('This installation is already paired')
            existing = cfg.get('pairing_request', {})
            if existing.get('status') in ('submitting', 'pending', 'cancelling'):
                raise ValueError('A pairing request is already in progress')
            # Save the proof before any network request. Restarts or lost replies
            # retry the same request, rather than mailing duplicate requests.
            cfg = {'name': name.strip(), 'upload_key': secrets.token_hex(32),
                   'pairing_request': {'id': secrets.token_hex(16), 'status': 'submitting',
                                       'contact_email': email, 'notification': 'retrying'}}
            self.save_config(cfg)
            self.pair_next = 0
            self.error = None
            result = self.status()
        self.start(); self.wake.set(); self.on_change()
        return result

    def cancel_request(self):
        with self.lock:
            cfg = self.read_config()
            if cfg.get('installation_id'):
                raise ValueError('Already paired; revoke upload access on the website')
            if not cfg.get('pairing_request'):
                raise ValueError('No pairing request to cancel')
            cfg['pairing_request']['status'] = 'cancelling'
            self.save_config(cfg)
            self.pair_next = 0
            result = self.status()
        self.start(); self.wake.set(); self.on_change()
        return result

    def check_pairing(self):
        with self.lock:
            cfg = self.read_config()
            pending = cfg.get('pairing_request')
            if (cfg.get('installation_id') or not pending
                    or pending.get('status') not in ('submitting', 'pending', 'cancelling')
                    or time.monotonic() < self.pair_next):
                return False
            self.pair_next = time.monotonic() + 30
            payload = {'request_id': pending['id'], 'upload_key': cfg['upload_key']}
            action = {'submitting': 'request-pairing', 'pending': 'pairing-status',
                      'cancelling': 'cancel-pairing-request'}[pending['status']]
            if action == 'request-pairing':
                payload.update(name=cfg['name'], contact_email=pending['contact_email'])
            try:
                reply = self.transport(action, payload)
                state = reply.get('status')
                if (reply.get('ok') is not True or reply.get('request_id') != pending['id']
                        or state not in ('pending', 'approved', 'rejected', 'cancelled', 'expired', 'revoked')):
                    raise ValueError('Pairing acknowledgement did not match the request')
                if action == 'cancel-pairing-request':
                    if state != 'cancelled':
                        raise ValueError('Pairing cancellation was not acknowledged')
                    self.path.unlink()
                    self.paired = False
                else:
                    if state == 'approved':
                        iid = reply.get('installation_id')
                        if not isinstance(iid, str) or not re.fullmatch(r'[a-f0-9]{32}', iid):
                            raise ValueError('Invalid pairing acknowledgement')
                        cfg['installation_id'] = iid
                    pending.update(status=state, notification=reply.get('notification', 'retrying'),
                                   expires=reply.get('expires'))
                    self.save_config(cfg)
                self.error = None
            except Exception as exc:
                self.error = str(exc) if isinstance(exc, ValueError) else 'Pairing service unavailable; retrying automatically'
                return False
        self.on_change()
        return bool(cfg.get('installation_id'))

    def pair(self, code, name):
        if not isinstance(code, str) or not re.fullmatch(r'[A-Za-z0-9-]{20,60}', code.strip()):
            raise ValueError('Enter the one-time pairing code from the scoreboard administrator')
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
            raise ValueError('Enter an installation name (1–80 characters)')
        with self.lock:
            config = self.read_config()
            if config.get('installation_id'):
                raise ValueError('Already paired. Revoke it on the website and disconnect locally before pairing again.')
            if config.get('pairing_request', {}).get('status') in ('submitting', 'pending', 'cancelling'):
                raise ValueError('Cancel the pending request before using a manual pairing code')
            # Persist proof before the request: safe retry if the response is lost.
            config.setdefault('upload_key', secrets.token_hex(32))
            config['name'] = name.strip()
            self.save_config(config)
            reply = self.transport('pair', {'code': code.strip(), 'name': config['name'], 'upload_key': config['upload_key']})
            installation = reply.get('installation_id')
            if not isinstance(installation, str) or not re.fullmatch(r'[a-f0-9]{32}', installation):
                raise ValueError('Invalid pairing acknowledgement')
            config.pop('pairing_request', None)
            config['installation_id'] = installation
            self.save_config(config)
            self.error = None
        self.wake.set(); self.on_change()
        return self.status()

    def disconnect(self):
        with self.lock:
            cfg = self.read_config()
            if not cfg.get('installation_id') and cfg.get('pairing_request'):
                return self.cancel_request()
            if self.path.exists():
                self.path.unlink()
            self.paired = False
            self.error = None
        self.on_change()

    def status(self):
        with self.lock:
            try:
                cfg = self.read_config()
            except Exception:
                cfg = {}; self.error = 'Cannot read installation configuration'
            with self.store.transaction() as db:
                pending = db.execute('SELECT count(*) FROM score_outbox').fetchone()[0]
                row = db.execute('SELECT error FROM score_outbox WHERE error IS NOT NULL ORDER BY rowid LIMIT 1').fetchone()
            return {'paired': bool(cfg.get('installation_id')), 'name': cfg.get('name'),
                    'installation_id': cfg.get('installation_id'), 'pending': pending,
                    'pairing_request': cfg.get('pairing_request'),
                    'error': self.error or (row[0] if row else None), 'url': 'https://mecharena.eu/score'}

    def flush_one(self):
        with self.lock:
            cfg = self.read_config()
            if not cfg.get('installation_id'):
                return False
            with self.store.transaction() as db:
                # Preserve order: profile registration must precede its results.
                row = db.execute('SELECT * FROM score_outbox ORDER BY rowid LIMIT 1').fetchone()
            if not row or row['next_at'] > time.time():
                return False
            try:
                reply = self.transport('ingest', json.loads(row['payload']), cfg['upload_key'])
                if reply.get('accepted_id') != row['id']:
                    raise ValueError('Upload acknowledgement did not match the queued record')
                with self.store.transaction(write=True) as db:
                    db.execute('DELETE FROM score_outbox WHERE id=? AND payload=?', (row['id'], row['payload']))
                self.error = None
            except Exception as exc:
                self.error = str(exc) if isinstance(exc, ValueError) else 'Upload unavailable; will retry automatically'
                with self.store.transaction(write=True) as db:
                    db.execute('UPDATE score_outbox SET tries=tries+1,next_at=?,error=? WHERE id=? AND payload=?',
                        (time.time() + min(900, 5 * 2 ** min(row['tries'], 8)), self.error, row['id'], row['payload']))
                return False
        self.on_change()
        return True

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        def run():
            while not self.stop_event.is_set():
                try:
                    if self.check_pairing():
                        continue
                    if self.flush_one():
                        continue
                except Exception:
                    self.error = 'Scoreboard uploader unavailable; local results are saved'
                self.wake.wait(10); self.wake.clear()
        self.thread = threading.Thread(target=run, name='scoreboard-upload', daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set(); self.wake.set()
        if self.thread:
            self.thread.join(timeout=16)
