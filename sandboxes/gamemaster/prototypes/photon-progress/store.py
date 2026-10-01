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
SCHEMA = 2
LESSON_VERSION = 1
TEST_PLAYERS = {'ltz-test-green': 'Test player · Green', 'ltz-test-purple': 'Test player · Purple'}


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
        if self.path.exists():
            with sqlite3.connect(self.path) as source:
                if source.execute('PRAGMA user_version').fetchone()[0] == 1:
                    backup = self.path.with_suffix('.pre-v2.sqlite3')
                    if not backup.exists():
                        with sqlite3.connect(backup) as target:
                            source.backup(target)
        with self.transaction(write=True) as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1, SCHEMA):
                raise ValueError('unsupported progress database version')
            db.execute('CREATE TABLE IF NOT EXISTS players(id TEXT PRIMARY KEY, data TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS sessions(side TEXT PRIMARY KEY CHECK(side IN (\'green\',\'purple\')), player_id TEXT UNIQUE REFERENCES players(id))')
            db.execute('CREATE TABLE IF NOT EXISTS attempts(id TEXT PRIMARY KEY, data TEXT NOT NULL)')
            db.execute("CREATE INDEX IF NOT EXISTS attempt_outcome ON attempts(json_extract(data,'$.outcome'))")
            db.execute('CREATE TABLE IF NOT EXISTS participants(run_id TEXT REFERENCES attempts(id), player_id TEXT REFERENCES players(id), PRIMARY KEY(run_id,player_id))')
            db.execute('CREATE TABLE IF NOT EXISTS ledger(id TEXT PRIMARY KEY, player_id TEXT REFERENCES players(id), amount INTEGER NOT NULL, data TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS operations(id TEXT PRIMARY KEY, data TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS ready_rosters(id TEXT PRIMARY KEY, data TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS lesson_rosters(id TEXT PRIMARY KEY, data TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value INTEGER NOT NULL)')
            db.execute("INSERT OR IGNORE INTO meta VALUES('revision',1)")
            if version == 1:
                for row in db.execute('SELECT id,data FROM players').fetchall():
                    player = self._migrate_player(json.loads(row['data']))
                    db.execute('UPDATE players SET data=? WHERE id=?', (encoded(player), row['id']))
            for player_id, name in TEST_PLAYERS.items():
                player = self._new_player(player_id, name, created_at=0)
                if db.execute('INSERT OR IGNORE INTO players VALUES(?,?)', (player_id, encoded(player))).rowcount:
                    self._touch(db)
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
        player = json.loads(row[0])
        player['is_test'] = player_id in TEST_PLAYERS
        return player

    @staticmethod
    def _new_player(player_id, name, *, created_at=None):
        return {'id': player_id, 'name': name, 'created_at': time.time() if created_at is None else created_at,
                'revision': 1, 'is_test': player_id in TEST_PLAYERS,
                'selected_control': 1, 'unlocked_control': 1, 'wins_by_tier': [0, 0, 0, 0],
                'current_control_tier': 1, 'progression_stage': 'playing',
                'lesson': {'version': LESSON_VERSION, 'complete': False}, 'calibration_milestone': None,
                'levels': {track: 1 for track in TRACKS}, 'credits': 0, 'lifetime_score': 0,
                'attempts': 0, 'wins': 0}

    @staticmethod
    def _put_player(db, player):
        player['revision'] += 1
        db.execute('UPDATE players SET data=? WHERE id=?', (encoded(player), player['id']))

    @staticmethod
    def _idle(db, player_id, reservation_id=None, changing_profile=False):
        for row in db.execute('SELECT a.data FROM attempts a JOIN participants p ON a.id=p.run_id WHERE p.player_id=?', (player_id,)):
            if json.loads(row[0])['outcome'] == 'running':
                raise ValueError('finish the active attempt before changing this player')
        for row in db.execute('SELECT id,data FROM ready_rosters'):
            reservation = json.loads(row['data'])
            if row['id'] != reservation_id and any(p['player_id'] == player_id for p in reservation['participants']):
                raise ValueError('the ready roster is fixed; wait for the next upgrade phase')
        if changing_profile:
            for row in db.execute('SELECT data FROM lesson_rosters'):
                if player_id in json.loads(row['data']).values():
                    raise ValueError('the calibration roster is fixed; finish both calibration turns first')

    @staticmethod
    def _migrate_player(player):
        tier = integer(player.get('unlocked_control', 1), 1, 4)
        wins = player.get('wins_by_tier')
        if not isinstance(wins, list) or len(wins) != 4 or any(type(w) is not int or w < 0 for w in wins):
            raise ValueError('invalid mastery records; operator recovery required')
        if any(w < 3 for w in wins[:tier-1]):
            raise ValueError('inconsistent earned tiers; operator recovery required')
        player.update(current_control_tier=tier, selected_control=tier,
                      progression_stage='calibration_pending' if tier >= 3 else 'playing',
                      lesson={'version': LESSON_VERSION, 'complete': False},
                      calibration_milestone=f'legacy:{player["id"]}' if tier >= 3 else None)
        return player

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

    def create_player(self, name, operation_id, *, side=None):
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 32 or any(ord(c) < 32 for c in name):
            raise ValueError('player name must contain 1–32 printable characters')
        intent = {'action': 'create', 'name': name.strip()}
        if side is not None:
            if side not in ('green', 'purple'):
                raise ValueError('invalid side')
            intent['side'] = side
        with self.transaction(write=True) as db:
            previous = self._operation(db, operation_id, intent)
            if previous is not None:
                return previous
            player = self._new_player(uuid.uuid4().hex, name.strip())
            db.execute('INSERT INTO players VALUES(?,?)', (player['id'], encoded(player)))
            if side is not None:
                self._select_player(db, side, player['id'])
            result = {'player_id': player['id']}
            self._remember(db, operation_id, intent, result)
            self._touch(db)
            return result

    def select_player(self, side, player_id):
        if side not in ('green', 'purple'):
            raise ValueError('invalid side')
        with self.transaction(write=True) as db:
            self._select_player(db, side, player_id)
            self._touch(db)

    def _select_player(self, db, side, player_id):
        current = db.execute('SELECT player_id FROM sessions WHERE side=?', (side,)).fetchone()
        if current:
            self._idle(db, current[0], changing_profile=True)
        if player_id:
            self._player(db, player_id)
            self._idle(db, player_id, changing_profile=True)
            other = db.execute('SELECT side FROM sessions WHERE player_id=? AND side!=?', (player_id, side)).fetchone()
            if other:
                raise ValueError('player is selected on the other side; release them there first')
        db.execute('DELETE FROM sessions WHERE side=?', (side,))
        if player_id:
            db.execute('INSERT INTO sessions VALUES(?,?)', (side, player_id))

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
            if player['is_test']:
                raise ValueError('test profiles use Game Master test unlocks and test loadouts; earned upgrades are unchanged')
            if data.get('action') == 'control':
                level = integer(data.get('level'), 1, 4)
                if level != player['current_control_tier']:
                    raise ValueError('stay on your current tier until three wins advance you')
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
            for player in players:
                player['is_test'] = player['id'] in TEST_PLAYERS
            roster = {row['side']: row['player_id'] for row in db.execute('SELECT * FROM sessions')}
            by_id = {player['id']: player for player in players}
            active = [json.loads(row[0]) for row in db.execute("SELECT data FROM attempts WHERE json_extract(data,'$.outcome')='running'")]
            return {'revision': db.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0],
                    'players': [{'id': p['id'], 'name': p['name'], 'is_test': p['is_test']} for p in sorted(players, key=lambda p: (not p['is_test'], p['name'].casefold(), p['id']))],
                    'roster': {team: by_id[pid] for team, pid in roster.items()},
                    'player': by_id.get(roster.get(side)),
                    'active_attempts': [{'run_id': a['run_id'], 'reward_enabled': a['reward_enabled'], 'participants': a['participants'], 'banked_kills': a['kills']} for a in active]}

    def control_policy(self, side):
        if side not in ('green', 'purple'):
            raise ValueError('invalid side')
        with self.transaction() as db:
            for row in db.execute("SELECT data FROM attempts WHERE json_extract(data,'$.outcome')='running'"):
                attempt = json.loads(row[0])
                if not attempt['reward_enabled']:
                    continue
                for participant in attempt['participants']:
                    if participant['side'] == side:
                        return {'active': True, 'run_id': attempt['run_id'], 'tier': participant['control_tier'], 'stage': 'playing'}
                # An unregistered side cannot assist a scored run.
                return {'active': True, 'run_id': attempt['run_id'], 'tier': 0}
            selected = db.execute('SELECT player_id FROM sessions WHERE side=?', (side,)).fetchone()
            if selected:
                player = self._player(db, selected[0])
                return {'active': False, 'tier': player['current_control_tier'],
                        'stage': player['progression_stage'], 'player_id': player['id']}
        return {'active': False, 'tier': 0, 'stage': 'unselected'}

    def reserve_lesson_roster(self, reservation_id):
        identifier(reservation_id)
        with self.transaction(write=True) as db:
            roster = {row['side']: row['player_id'] for row in db.execute('SELECT * FROM sessions')}
            if set(roster) != {'green', 'purple'}:
                raise ValueError('both players must remain selected during calibration')
            saved = db.execute('SELECT data FROM lesson_rosters WHERE id=?', (reservation_id,)).fetchone()
            if saved:
                if json.loads(saved[0]) != roster:
                    raise ValueError('calibration participants changed')
                return roster
            db.execute('INSERT INTO lesson_rosters VALUES(?,?)', (reservation_id, encoded(roster)))
            self._touch(db)
            return roster

    def reserve_roster(self, reservation_id, expected_players=None):
        identifier(reservation_id)
        with self.transaction(write=True) as db:
            saved = db.execute('SELECT data FROM ready_rosters WHERE id=?', (reservation_id,)).fetchone()
            if saved:
                return json.loads(saved[0])
            participants = []
            for row in db.execute('SELECT * FROM sessions ORDER BY side'):
                p = self._player(db, row['player_id'])
                if expected_players is not None and expected_players.get(row['side'])!={'id':p['id'],'revision':p['revision']}:
                    raise ValueError('ready profile changed while starting; confirm Ready again')
                self._idle(db, p['id'])
                if p['progression_stage'] != 'playing':
                    raise ValueError('complete required calibration before becoming ready')
                participants.append({'player_id': p['id'], 'name': p['name'], 'side': row['side'],
                                     'control_tier': p['current_control_tier'], 'levels': p['levels']})
            if len(participants) != 2:
                raise ValueError('both Green and Purple must select saved players')
            result = {'id': reservation_id, 'participants': participants}
            db.execute('INSERT INTO ready_rosters VALUES(?,?)', (reservation_id, encoded(result)))
            self._touch(db)
            return result

    def release_roster(self, reservation_id):
        with self.transaction(write=True) as db:
            db.execute('DELETE FROM ready_rosters WHERE id=?', (identifier(reservation_id),))
            db.execute('DELETE FROM lesson_rosters WHERE id=?', (reservation_id,))
            self._touch(db)

    def complete_lesson(self, value):
        player_id = identifier(value.get('player_id'))
        operation_id = identifier(value.get('operation_id'))
        integer(value.get('calibration_revision'), 1)
        if value.get('lesson_version') != LESSON_VERSION or not isinstance(value.get('evidence_id'), str) or not 1<=len(value['evidence_id'])<=500:
            raise ValueError('validated lesson evidence required')
        with self.transaction(write=True) as db:
            previous = self._operation(db, operation_id, value)
            if previous is not None:
                return previous
            p = self._player(db, player_id)
            if p['current_control_tier'] < 3 or p['calibration_milestone'] != value.get('milestone_id'):
                raise ValueError('this player has not reached the calibration milestone')
            p['lesson'] = {'version': LESSON_VERSION, 'complete': True, 'receipt': dict(value), 'completed_at': time.time()}
            p['progression_stage'] = 'playing'
            self._put_player(db, p)
            result = {'player_id': p['id'], 'revision': p['revision']}
            self._remember(db, operation_id, value, result)
            self._touch(db)
            return result

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
                if saved['metadata'] != meta or saved.get('requested_reward_enabled', saved['reward_enabled']) != data['reward_enabled']:
                    raise ValueError('run ID already used for another attempt')
                return saved
            participants = []
            for row in db.execute('SELECT * FROM sessions ORDER BY side'):
                p = self._player(db, row['player_id'])
                self._idle(db, p['id'], data.get('reservation_id'))
                participants.append({'player_id': p['id'], 'name': p['name'], 'side': row['side'],
                                     'control_tier': p['current_control_tier'], 'levels': p['levels']})
            test_players = [p['player_id'] for p in participants if p['player_id'] in TEST_PLAYERS]
            reward_enabled = data['reward_enabled'] and not test_players
            if reward_enabled and any(self._player(db, p['player_id'])['progression_stage'] != 'playing' for p in participants):
                raise ValueError('complete required calibration before scored play')
            if reward_enabled and len(participants) != 2:
                raise ValueError('both Green and Purple must select saved players before scored play')
            if data.get('reservation_id'):
                ready = db.execute('SELECT data FROM ready_rosters WHERE id=?', (identifier(data['reservation_id']),)).fetchone()
                if not ready or json.loads(ready[0])['participants'] != participants:
                    raise ValueError('ready roster changed; operator recovery required')
            expected = data.get('expected_roster')
            if expected is not None and expected != participants:
                raise ValueError('players changed while preparing the run; retry Start')
            attempt = {'run_id': run_id, 'started_at': time.time(), 'finished_at': None,
                       'outcome': 'running', 'reward_enabled': reward_enabled, 'metadata': meta,
                       'requested_reward_enabled': data['reward_enabled'], 'test_player_ids': test_players,
                       'practice_reason': 'test_player' if test_players else None,
                       'participants': participants, 'kills': 0, 'sequence': 0, 'result': None}
            db.execute('INSERT INTO attempts VALUES(?,?)', (run_id, encoded(attempt)))
            if data.get('reservation_id'):
                db.execute('DELETE FROM ready_rosters WHERE id=?', (data['reservation_id'],))
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
            if data.get('telemetry') is not None and (not isinstance(data['telemetry'],dict) or len(encoded(data['telemetry']))>20000):
                raise ValueError('invalid result telemetry')
        with self.transaction(write=True) as db:
            a = self._attempt(db, run_id)
            recovered_result = False
            if a['outcome'] != 'running':
                if not final or a['result'] == data:
                    return a
                previous = a['result'] or {}
                # Recovery can race a still-running older Game process. Its
                # synthetic interruption is provisional; a newer durable final
                # result supersedes it without counting the attempt twice.
                legacy_recovery = set(previous) == {'run_id', 'kills', 'sequence', 'outcome', 'active_seconds', 'finished_at', 'released_orcs'}
                interrupted = (a['outcome'] == 'interrupted' and previous.get('active_seconds') == 0
                               and previous.get('released_orcs') == 0
                               and (previous.get('recovery_interrupted') is True or legacy_recovery))
                if not (interrupted and outcome != 'interrupted' and sequence > a['sequence']
                        and kills >= a['kills'] and data['finished_at'] >= a['finished_at']):
                    raise ValueError('conflicting final result')
                a['interrupted_result'] = previous
                recovered_result = True
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
                    if not recovered_result:
                        p['attempts'] += 1
                    if outcome == 'won':
                        previous_tier = p['current_control_tier']
                        p['wins'] += 1
                        tier = participant['control_tier']
                        p['wins_by_tier'][tier - 1] += 1
                        if tier == previous_tier and tier < 4 and p['wins_by_tier'][tier-1] >= 3:
                            p['current_control_tier'] += 1
                            p['selected_control'] = p['unlocked_control'] = p['current_control_tier']
                            a.setdefault('unlocks', {})[p['id']] = p['current_control_tier']
                            if tier == 2:
                                p['progression_stage'] = 'calibration_pending'
                                p['calibration_milestone'] = f'{run_id}:{p["id"]}'
                                a.setdefault('calibration_milestones', {})[p['id']] = p['calibration_milestone']
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
                             'outcome': 'interrupted', 'active_seconds': 0, 'finished_at': time.time(), 'released_orcs': 0,
                             'recovery_interrupted': True}, final=True)

    def attempt(self, run_id):
        with self.transaction() as db:
            row=db.execute('SELECT data FROM attempts WHERE id=?',(identifier(run_id),)).fetchone()
            if row is None:raise ValueError('attempt not found')
            return json.loads(row[0])

    def history(self, player_id, query):
        with self.transaction() as db:
            if query.get('combined'):
                attempts = [json.loads(row[0]) for row in db.execute('SELECT data FROM attempts')]
            else:
                self._player(db, player_id)
                attempts = [json.loads(row[0]) for row in db.execute('SELECT a.data FROM attempts a JOIN participants p ON a.id=p.run_id WHERE p.player_id=?', (player_id,))]
        rows = []
        dataset = query.get('dataset', 'scored')
        if dataset not in ('scored', 'practice'):
            raise ValueError('invalid history dataset')
        for a in attempts:
            if a['outcome'] == 'running' or a['reward_enabled'] != (dataset == 'scored'):
                continue
            if not a['participants']:
                continue
            p = next((p for p in a['participants'] if (p['side']==query['side_at_run'] if query.get('combined') and query.get('side_at_run') else p['player_id']==player_id)), a['participants'][0])
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
                   'released_orcs': result.get('released_orcs'),'telemetry':result.get('telemetry'), 'metadata': meta, 'cohort': cohort,
                   'calibration_milestones':a.get('calibration_milestones',{})}
            row['participants'] = [{k: participant[k] for k in ('player_id', 'name', 'side', 'control_tier', 'levels')} for participant in a['participants']]
            if query.get('side_at_run') and p['side']!=query['side_at_run']:
                continue
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
        # Changes compare successful runs only; individual failures remain visible.
        won_scores=[r['score'] for r in rows if r['outcome']=='won']
        summary = {'attempts': len(rows), 'wins': sum(r['outcome'] == 'won' for r in rows),
                   'comparable': comparable, 'best_score': max(scores) if scores and comparable else None,
                   'best_time': min(times) if times and comparable else None,
                   'score_change': change(won_scores), 'time_change': change(times, True)}
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
        if not isinstance(backup, dict) or type(backup.get('schema_version')) is not int or backup['schema_version'] not in (1, SCHEMA):
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
                    if 'is_test' in p and (type(p['is_test']) is not bool or p['is_test'] != (p['id'] in TEST_PLAYERS)):
                        raise ValueError('invalid saved test-player classification')
                    if row['id'] in TEST_PLAYERS and p != self._new_player(row['id'], TEST_PLAYERS[row['id']], created_at=0):
                        raise ValueError('built-in test profiles cannot contain earned progress')
                    if backup['schema_version'] == 1:
                        p = self._migrate_player(p)
                        row['data'] = encoded(p)
                    if 'damage-photon' in p.get('levels', {}):
                        old = p['levels'].pop('damage-photon')
                        p['levels']['damage-tesla-coil'] = max(old, p['levels'].get('damage-tesla-coil', 1))
                        row['data'] = encoded(p)
                    if p.get('id') != row['id'] or set(p.get('levels', {})) != set(TRACKS):
                        raise ValueError('invalid saved player')
                    for level in p['levels'].values():
                        integer(level, 1, 4)
                    integer(p['selected_control'], 1, integer(p['unlocked_control'], 1, 4))
                    if p['current_control_tier'] != p['selected_control'] or p['selected_control'] != p['unlocked_control']:
                        raise ValueError('saved required tier is inconsistent')
                    if p['progression_stage'] not in ('playing', 'calibration_pending') or type(p['lesson'].get('complete')) is not bool:
                        raise ValueError('invalid lesson state')
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
                    if a['reward_enabled'] and any(p['player_id'] in TEST_PLAYERS for p in a['participants']):
                        raise ValueError('test-player attempts cannot be scored')
                    if not isinstance(a.get('result'), dict) or a['result'].get('outcome') != a['outcome'] or a['result'].get('kills') != a['kills']:
                        raise ValueError('invalid saved result')
                if table == 'ledger':
                    integer(row['amount'], -1000000000)
        with self.transaction(write=True) as db:
            if db.execute('SELECT 1 FROM ready_rosters LIMIT 1').fetchone() or db.execute('SELECT 1 FROM lesson_rosters LIMIT 1').fetchone():
                raise ValueError('finish the shared ready/calibration phase before loading a backup')
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
