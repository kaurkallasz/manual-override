"""Transactional, module-owned player progress. No gameplay or sibling imports."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import statistics
import threading
import time
import uuid

TRACKS = ('damage-machine-gun', 'damage-flamethrower', 'damage-mortar', 'damage-tesla-coil', 'forcefield')
MODES = ('joint', 'xyz', 'image', 'cue')
SCHEMA = 1


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def integer(value, low=0, high=1000000000):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'expected an integer between {low} and {high}')
    return value


def identifier(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 160 or not all(c.isalnum() or c in '-_:.' for c in value):
        raise ValueError('invalid identifier')
    return value


def finite(value, low=0):
    if type(value) not in (int, float) or not math.isfinite(value) or value < low:
        raise ValueError('invalid numeric value')
    return value


def fingerprint(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def normalize_legacy_tracks(value):
    if isinstance(value, list):
        return [normalize_legacy_tracks(item) for item in value]
    if not isinstance(value, dict):
        return value
    value = {key: normalize_legacy_tracks(item) for key, item in value.items()}
    if 'damage-photon' in value:
        old = integer(value.pop('damage-photon'), 1, 4)
        value['damage-tesla-coil'] = max(old, integer(value.get('damage-tesla-coil', 1), 1, 4))
    if value.get('track') == 'damage-photon':
        value['track'] = 'damage-tesla-coil'
    return value


class ProgressStore:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.RLock()

    @contextmanager
    def transaction(self, *, write=False):
        with self.lock:
            db = sqlite3.connect(self.path, timeout=5)
            db.row_factory = sqlite3.Row
            try:
                db.execute('PRAGMA foreign_keys=ON')
                db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.transaction(write=True) as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, SCHEMA):
                raise ValueError('unsupported progress database version')
            db.execute('CREATE TABLE IF NOT EXISTS players(id TEXT PRIMARY KEY, data TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS sessions(side TEXT PRIMARY KEY CHECK(side IN (\'green\',\'purple\')), player_id TEXT UNIQUE REFERENCES players(id))')
            db.execute('CREATE TABLE IF NOT EXISTS attempts(id TEXT PRIMARY KEY, data TEXT NOT NULL)')
            db.execute("CREATE INDEX IF NOT EXISTS attempt_outcome ON attempts(json_extract(data,'$.outcome'))")
            db.execute('CREATE TABLE IF NOT EXISTS participants(run_id TEXT REFERENCES attempts(id), player_id TEXT REFERENCES players(id), PRIMARY KEY(run_id,player_id))')
            db.execute('CREATE TABLE IF NOT EXISTS ledger(id TEXT PRIMARY KEY, player_id TEXT REFERENCES players(id), amount INTEGER NOT NULL, data TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS operations(id TEXT PRIMARY KEY, data TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value INTEGER NOT NULL)')
            db.execute("INSERT OR IGNORE INTO meta VALUES('revision',1)")
            db.execute(f'PRAGMA user_version={SCHEMA}')
            if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise ValueError('progress database integrity check failed')

    @staticmethod
    def _touch(db):
        db.execute("UPDATE meta SET value=value+1 WHERE key='revision'")

    @staticmethod
    def _player(db, player_id):
        row = db.execute('SELECT data FROM players WHERE id=?', (player_id,)).fetchone()
        if row is None:
            raise ValueError('player not found')
        return json.loads(row[0])

    @staticmethod
    def _put_player(db, player):
        player['revision'] += 1
        db.execute('UPDATE players SET data=? WHERE id=?', (encoded(player), player['id']))

    @staticmethod
    def _idle(db, player_id):
        for row in db.execute('SELECT a.data FROM attempts a JOIN participants p ON a.id=p.run_id WHERE p.player_id=?', (player_id,)):
            if json.loads(row[0])['outcome'] == 'running':
                raise ValueError('finish the active attempt before changing this player')

    @staticmethod
    def _operation(db, operation_id, intent):
        identifier(operation_id)
        saved = db.execute('SELECT data FROM operations WHERE id=?', (operation_id,)).fetchone()
        if saved:
            saved = json.loads(saved[0])
            if saved['intent'] != intent:
                raise ValueError('operation ID already used for another request')
            return saved['result']
        return None

    @staticmethod
    def _remember(db, operation_id, intent, result):
        db.execute('INSERT INTO operations VALUES(?,?)', (operation_id, encoded({'intent': intent, 'result': result})))

    def create_player(self, name, operation_id):
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 32 or any(ord(c) < 32 for c in name):
            raise ValueError('player name must contain 1–32 printable characters')
        intent = {'action': 'create', 'name': name.strip()}
        with self.transaction(write=True) as db:
            previous = self._operation(db, operation_id, intent)
            if previous is not None:
                return previous
            player = {'id': uuid.uuid4().hex, 'name': name.strip(), 'created_at': time.time(), 'revision': 1,
                      'selected_control': 1, 'unlocked_control': 1, 'wins_by_tier': [0, 0, 0, 0],
                      'levels': {track: 1 for track in TRACKS}, 'credits': 0, 'lifetime_score': 0,
                      'attempts': 0, 'wins': 0}
            db.execute('INSERT INTO players VALUES(?,?)', (player['id'], encoded(player)))
            result = {'player_id': player['id']}
            self._remember(db, operation_id, intent, result)
            self._touch(db)
            return result

    def select_player(self, side, player_id):
        if side not in ('green', 'purple'):
            raise ValueError('invalid side')
        with self.transaction(write=True) as db:
            current = db.execute('SELECT player_id FROM sessions WHERE side=?', (side,)).fetchone()
            if current:
                self._idle(db, current[0])
            if player_id:
                self._player(db, player_id)
                self._idle(db, player_id)
                other = db.execute('SELECT side FROM sessions WHERE player_id=? AND side!=?', (player_id, side)).fetchone()
                if other:
                    raise ValueError('player is selected on the other side; release them there first')
            db.execute('DELETE FROM sessions WHERE side=?', (side,))
            if player_id:
                db.execute('INSERT INTO sessions VALUES(?,?)', (side, player_id))
            self._touch(db)

    def mutate_player(self, side, data):
        with self.transaction(write=True) as db:
            row = db.execute('SELECT player_id FROM sessions WHERE side=?', (side,)).fetchone()
            if row is None:
                raise ValueError('select a player first')
            player = self._player(db, row[0])
            intent = {'side': side, 'player_id': player['id'], **data}
            operation_id = data.get('operation_id')
            previous = self._operation(db, operation_id, intent)
            if previous is not None:
                return previous
            self._idle(db, player['id'])
            if data.get('revision') != player['revision']:
                raise ValueError('player changed in another window; refresh and retry')
            if data.get('action') == 'control':
                level = integer(data.get('level'), 1, 4)
                if level > player['unlocked_control']:
                    raise ValueError('complete the preceding level three times to unlock this control')
                player['selected_control'] = level
            elif data.get('action') == 'purchase':
                track = data.get('track')
                level = integer(data.get('level'), 2, 4)
                if track not in TRACKS or player['levels'][track] + 1 != level:
                    raise ValueError('only the next level of a supported upgrade can be purchased')
                cost = (1000 if track == 'forcefield' else 250) * (level - 1)
                if player['credits'] < cost:
                    raise ValueError(f'need {cost - player["credits"]} more credits')
                player['credits'] -= cost
                player['levels'][track] = level
                db.execute('INSERT INTO ledger VALUES(?,?,?,?)', (operation_id, player['id'], -cost, encoded({'kind': 'purchase', 'track': track, 'level': level, 'at': time.time()})))
            else:
                raise ValueError('unknown player action')
            self._put_player(db, player)
            result = {'player_id': player['id'], 'revision': player['revision']}
            self._remember(db, operation_id, intent, result)
            self._touch(db)
            return result

    def snapshot(self, side=None):
        with self.transaction() as db:
            players = [json.loads(row[0]) for row in db.execute('SELECT data FROM players ORDER BY id')]
            roster = {row['side']: row['player_id'] for row in db.execute('SELECT * FROM sessions')}
            by_id = {player['id']: player for player in players}
            active = [json.loads(row[0]) for row in db.execute("SELECT data FROM attempts WHERE json_extract(data,'$.outcome')='running'")]
            return {'revision': db.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0],
                    'players': [{'id': p['id'], 'name': p['name']} for p in sorted(players, key=lambda p: (p['name'].casefold(), p['id']))],
                    'roster': {team: by_id[pid] for team, pid in roster.items()},
                    'player': by_id.get(roster.get(side)),
                    'active_attempts': [{'run_id': a['run_id'], 'reward_enabled': a['reward_enabled'], 'participants': a['participants'], 'banked_kills': a['kills']} for a in active]}

    def control_policy(self, side):
        with self.transaction() as db:
            for row in db.execute("SELECT data FROM attempts WHERE json_extract(data,'$.outcome')='running'"):
                attempt = json.loads(row[0])
                if not attempt['reward_enabled']:
                    continue
                for participant in attempt['participants']:
                    if participant['side'] == side:
                        return {'active': True, 'run_id': attempt['run_id'], 'tier': participant['control_tier']}
                # An unregistered side cannot assist a scored run.
                return {'active': True, 'run_id': attempt['run_id'], 'tier': 0}
        return {'active': False}

    def begin(self, data):
        run_id = identifier(data.get('run_id'))
        if type(data.get('reward_enabled')) is not bool:
            raise ValueError('reward eligibility is required')
        meta = data.get('metadata')
        if not isinstance(meta, dict) or len(encoded(meta)) > 100000:
            raise ValueError('invalid attempt metadata')
        with self.transaction(write=True) as db:
            existing = db.execute('SELECT data FROM attempts WHERE id=?', (run_id,)).fetchone()
            if existing:
                saved = json.loads(existing[0])
                if saved['metadata'] != meta or saved['reward_enabled'] != data['reward_enabled']:
                    raise ValueError('run ID already used for another attempt')
                return saved
            participants = []
            for row in db.execute('SELECT * FROM sessions ORDER BY side'):
                p = self._player(db, row['player_id'])
                self._idle(db, p['id'])
                participants.append({'player_id': p['id'], 'name': p['name'], 'side': row['side'],
                                     'control_tier': p['selected_control'], 'levels': p['levels']})
            if data['reward_enabled'] and not participants:
                raise ValueError('select at least one saved player in LTZ Score before scored play')
            expected = data.get('expected_roster')
            if expected is not None and expected != participants:
                raise ValueError('players changed while preparing the run; retry Start')
            attempt = {'run_id': run_id, 'started_at': time.time(), 'finished_at': None,
                       'outcome': 'running', 'reward_enabled': data['reward_enabled'], 'metadata': meta,
                       'participants': participants, 'kills': 0, 'sequence': 0, 'result': None}
            db.execute('INSERT INTO attempts VALUES(?,?)', (run_id, encoded(attempt)))
            for participant in participants:
                db.execute('INSERT INTO participants VALUES(?,?)', (run_id, participant['player_id']))
            self._touch(db)
            return attempt

    @staticmethod
    def _attempt(db, run_id):
        row = db.execute('SELECT data FROM attempts WHERE id=?', (run_id,)).fetchone()
        if row is None:
            raise ValueError('unknown attempt')
        return json.loads(row[0])

    def record(self, data, *, final=False):
        run_id = identifier(data.get('run_id'))
        kills = integer(data.get('kills'))
        sequence = integer(data.get('sequence'), 1)
        outcome = data.get('outcome')
        if final:
            if outcome not in ('won', 'overrun', 'aborted', 'interrupted'):
                raise ValueError('invalid terminal outcome')
            finite(data.get('active_seconds'))
            finite(data.get('finished_at'))
            integer(data.get('released_orcs', 0))
        with self.transaction(write=True) as db:
            a = self._attempt(db, run_id)
            if a['outcome'] != 'running':
                if final and a['result'] != data:
                    raise ValueError('conflicting final result')
                return a
            if sequence <= a['sequence']:
                if final:
                    raise ValueError('stale terminal checkpoint')
                return a
            if kills < a['kills']:
                raise ValueError('kill checkpoints must be cumulative')
            delta = kills - a['kills']
            for participant in a['participants']:
                p = self._player(db, participant['player_id'])
                if a['reward_enabled'] and delta:
                    p['credits'] += delta
                    p['lifetime_score'] += delta
                    key = f'{run_id}:{sequence}:{p["id"]}'
                    db.execute('INSERT INTO ledger VALUES(?,?,?,?)', (key, p['id'], delta, encoded({'kind': 'earned', 'run_id': run_id, 'at': time.time()})))
                if final and a['reward_enabled']:
                    p['attempts'] += 1
                    if outcome == 'won':
                        previous_tier = p['unlocked_control']
                        p['wins'] += 1
                        tier = participant['control_tier']
                        p['wins_by_tier'][tier - 1] += 1
                        while p['unlocked_control'] < 4 and p['wins_by_tier'][p['unlocked_control'] - 1] >= 3:
                            p['unlocked_control'] += 1
                        if p['unlocked_control'] > previous_tier:
                            a.setdefault('unlocks', {})[p['id']] = p['unlocked_control']
                if a['reward_enabled'] and (delta or final):
                    self._put_player(db, p)
            a.update(kills=kills, sequence=sequence)
            if final:
                a.update(outcome=outcome, finished_at=data['finished_at'], result=data)
            db.execute('UPDATE attempts SET data=? WHERE id=?', (encoded(a), run_id))
            self._touch(db)
            return a

    def recover(self):
        """Called by Game only AFTER its durable pending results have replayed."""
        with self.transaction() as db:
            unfinished = [json.loads(row[0]) for row in db.execute('SELECT data FROM attempts')]
        for a in unfinished:
            if a['outcome'] == 'running':
                self.record({'run_id': a['run_id'], 'kills': a['kills'], 'sequence': a['sequence'] + 1,
                             'outcome': 'interrupted', 'active_seconds': 0, 'finished_at': time.time(), 'released_orcs': 0}, final=True)

    def history(self, player_id, query):
        with self.transaction() as db:
            self._player(db, player_id)
            attempts = [json.loads(row[0]) for row in db.execute('SELECT a.data FROM attempts a JOIN participants p ON a.id=p.run_id WHERE p.player_id=?', (player_id,))]
        rows = []
        dataset = query.get('dataset', 'scored')
        if dataset not in ('scored', 'practice'):
            raise ValueError('invalid history dataset')
        for a in attempts:
            if a['outcome'] == 'running' or a['reward_enabled'] != (dataset == 'scored'):
                continue
            p = next(p for p in a['participants'] if p['player_id'] == player_id)
            meta = a['metadata']
            result = a['result'] or {}
            cohort = fingerprint({'metadata': {k: v for k, v in meta.items() if k not in ('settings_revision',)},
                                  'loadouts': [{k: p[k] for k in ('side', 'control_tier', 'levels')} for p in a['participants']]})
            row = {'run_id': a['run_id'], 'finished_at': a['finished_at'], 'outcome': a['outcome'],
                   'score': a['kills'] if a['reward_enabled'] else 0, 'kills': a['kills'],
                   'active_seconds': None if a['outcome'] == 'interrupted' else result.get('active_seconds'),
                   'control_tier': p['control_tier'], 'side': p['side'], 'levels': p['levels'],
                   'partner': ' + '.join(other['name'] for other in a['participants'] if other['player_id'] != player_id) or 'Solo',
                   'completion_awarded': a['reward_enabled'] and a['outcome'] == 'won',
                   'unlocked_control': a.get('unlocks', {}).get(player_id),
                   'released_orcs': result.get('released_orcs'), 'metadata': meta, 'cohort': cohort}
            if query.get('tier') and p['control_tier'] != int(query['tier']):
                continue
            if query.get('level') and meta.get('level_id') != query['level']:
                continue
            if query.get('from') and a['finished_at'] < float(query['from']):
                continue
            if query.get('to') and a['finished_at'] > float(query['to']):
                continue
            rows.append(row)
        rows.sort(key=lambda r: (r['finished_at'], r['run_id']))
        cohorts = {}
        for row in rows:
            c = cohorts.setdefault(row['cohort'], {'id': row['cohort'], 'count': 0, 'tier': row['control_tier'], 'metadata': row['metadata']})
            c['count'] += 1
        if query.get('cohort'):
            rows = [r for r in rows if r['cohort'] == query['cohort']]
        comparable = len({r['cohort'] for r in rows}) == 1
        scores = [r['score'] for r in rows if r['outcome'] != 'interrupted']
        times = [r['active_seconds'] for r in rows if r['outcome'] == 'won' and r['active_seconds'] is not None]
        def change(values, reverse=False):
            if not comparable or len(values) < 6:
                return None
            before, after = statistics.mean(values[:3]), statistics.mean(values[-3:])
            delta = (before - after) if reverse else (after - before)
            return {'baseline': before, 'recent': after, 'absolute': delta, 'percent': delta / before * 100 if before else None}
        summary = {'attempts': len(rows), 'wins': sum(r['outcome'] == 'won' for r in rows),
                   'comparable': comparable, 'best_score': max(scores) if scores and comparable else None,
                   'best_time': min(times) if times and comparable else None,
                   'score_change': change(scores), 'time_change': change(times, True)}
        offset = max(0, int(query.get('cursor', 0)))
        limit = max(1, min(100, int(query.get('limit', 100))))
        return {'rows': rows[offset:offset + limit], 'total': len(rows), 'summary': summary,
                'cohorts': list(cohorts.values()), 'next_cursor': offset + limit if offset + limit < len(rows) else None}

    def export(self):
        with self.transaction() as db:
            return {'schema_version': SCHEMA, 'exported_at': time.time(), 'tables': {
                table: [dict(row) for row in db.execute(f'SELECT * FROM {table} ORDER BY 1')]
                for table in ('players', 'attempts', 'participants', 'ledger', 'operations')}}

    def import_backup(self, backup, *, preview=False):
        if not isinstance(backup, dict) or type(backup.get('schema_version')) is not int or backup['schema_version'] != SCHEMA:
            raise ValueError('unsupported backup schema')
        tables = backup.get('tables')
        columns = {'players': ('id', 'data'), 'attempts': ('id', 'data'), 'participants': ('run_id', 'player_id'),
                   'ledger': ('id', 'player_id', 'amount', 'data'), 'operations': ('id', 'data')}
        if not isinstance(tables, dict) or set(tables) != set(columns) or len(encoded(backup)) > 20000000:
            raise ValueError('invalid or oversized backup')
        for table, fields in columns.items():
            if not isinstance(tables[table], list) or len(tables[table]) > 100000:
                raise ValueError('invalid backup rows')
            seen = set()
            for row in tables[table]:
                if not isinstance(row, dict) or set(row) != set(fields):
                    raise ValueError('invalid backup columns')
                key = tuple(row[f] for f in fields[:2 if table == 'participants' else 1])
                for part in key:
                    identifier(part)
                if key in seen:
                    raise ValueError('duplicate backup row')
                seen.add(key)
                if 'data' in row:
                    value = normalize_legacy_tracks(json.loads(row['data']))
                    if not isinstance(value, dict):
                        raise ValueError('invalid saved record')
                    row['data'] = encoded(value)
                if table == 'players':
                    p = json.loads(row['data'])
                    if 'damage-photon' in p.get('levels', {}):
                        old = p['levels'].pop('damage-photon')
                        p['levels']['damage-tesla-coil'] = max(old, p['levels'].get('damage-tesla-coil', 1))
                        row['data'] = encoded(p)
                    if p.get('id') != row['id'] or set(p.get('levels', {})) != set(TRACKS):
                        raise ValueError('invalid saved player')
                    for level in p['levels'].values():
                        integer(level, 1, 4)
                    integer(p['selected_control'], 1, integer(p['unlocked_control'], 1, 4))
                    integer(p['credits']); integer(p['lifetime_score']); integer(p['attempts']); integer(p['wins'])
                    integer(p['revision'], 1)
                    finite(p['created_at'])
                    if not isinstance(p.get('name'), str) or not 1 <= len(p['name'].strip()) <= 32 or any(ord(c) < 32 for c in p['name']):
                        raise ValueError('invalid saved player name')
                    if p['credits'] > p['lifetime_score'] or p['wins'] > p['attempts']:
                        raise ValueError('invalid player totals')
                    if len(p['wins_by_tier']) != 4:
                        raise ValueError('invalid mastery')
                    for wins in p['wins_by_tier']:
                        integer(wins)
                    if sum(p['wins_by_tier']) != p['wins'] or any(w < 3 for w in p['wins_by_tier'][:p['unlocked_control']-1]):
                        raise ValueError('invalid mastery totals')
                if table == 'attempts':
                    a = json.loads(row['data'])
                    if a.get('run_id') != row['id'] or a.get('outcome') not in ('won', 'overrun', 'aborted', 'interrupted'):
                        raise ValueError('backups may contain only finished attempts; finish live games before exporting')
                    integer(a['kills'])
                    integer(a['sequence'], 1)
                    finite(a['started_at']); finite(a['finished_at'])
                    if type(a.get('reward_enabled')) is not bool or not isinstance(a.get('metadata'), dict) or not isinstance(a.get('participants'), list):
                        raise ValueError('invalid saved attempt')
                    participants = set()
                    for participant in a['participants']:
                        identifier(participant['player_id'])
                        integer(participant['control_tier'], 1, 4)
                        if participant['side'] not in ('green', 'purple') or participant['side'] in participants:
                            raise ValueError('invalid saved participants')
                        participants.add(participant['side'])
                        if set(participant['levels']) != set(TRACKS):
                            raise ValueError('invalid frozen upgrade loadout')
                        for level in participant['levels'].values():
                            integer(level, 1, 4)
                    if not isinstance(a.get('result'), dict) or a['result'].get('outcome') != a['outcome'] or a['result'].get('kills') != a['kills']:
                        raise ValueError('invalid saved result')
                if table == 'ledger':
                    integer(row['amount'], -1000000000)
        with self.transaction(write=True) as db:
            for row in db.execute('SELECT data FROM attempts'):
                if json.loads(row[0])['outcome'] == 'running':
                    raise ValueError('finish active attempts before loading a backup')
            additions, conflicts = [], []
            for table, fields in columns.items():
                for row in tables[table]:
                    keys = fields[:2] if table == 'participants' else fields[:1]
                    clause = ' AND '.join(f'{k}=?' for k in keys)
                    found = db.execute(f'SELECT * FROM {table} WHERE {clause}', tuple(row[k] for k in keys)).fetchone()
                    if found and dict(found) != row:
                        conflicts.append(f'{table}:{row[keys[0]]}')
                    elif not found:
                        additions.append((table, fields, row))
            if conflicts:
                raise ValueError('backup conflicts with existing records: ' + ', '.join(conflicts[:5]))
            # Inserts and FK validation run even in preview; the preview is rolled back.
            db.execute('SAVEPOINT preview')
            for table, fields, row in additions:
                db.execute(f'INSERT INTO {table} ({",".join(fields)}) VALUES({",".join("?" for _ in fields)})', tuple(row[f] for f in fields))
            if db.execute('PRAGMA foreign_key_check').fetchone():
                raise ValueError('backup has broken references')
            for row in tables['players']:
                player = self._player(db, row['id'])
                credits, lifetime = db.execute('SELECT COALESCE(SUM(amount),0), COALESCE(SUM(CASE WHEN amount>0 THEN amount ELSE 0 END),0) FROM ledger WHERE player_id=?', (row['id'],)).fetchone()
                if (credits, lifetime) != (player['credits'], player['lifetime_score']):
                    raise ValueError('backup player balance does not match its ledger')
            for row in tables['attempts']:
                attempt = json.loads(row['data'])
                members = {p['player_id'] for p in attempt['participants']}
                linked = {p[0] for p in db.execute('SELECT player_id FROM participants WHERE run_id=?', (row['id'],))}
                if members != linked or len(members) != len(attempt['participants']):
                    raise ValueError('backup participant references do not match its attempt')
            if preview:
                db.execute('ROLLBACK TO preview')
            else:
                self._touch(db)
            return {'new_records': len(additions), 'identical_records': sum(len(v) for v in tables.values()) - len(additions)}
