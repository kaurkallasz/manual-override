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

from ltz_economy import EconomyStore, initialize as initialize_economy, quote
from ltz_rewards import migrate_player, banks_kill_credits, validate as validate_reward, rule as validate_reward_rule
from ltz_records import encoded, integer, identifier, finite, fingerprint, normalize_legacy_tracks
from ltz_backup import BackupStore
from event_store import EventStore
from linked_games import LinkedGames
from level_results import LevelResults, attempts as event_attempts, statistics_at_finish, result_view, validate_heatmap

TRACKS = ('damage-machine-gun', 'damage-flamethrower', 'damage-mortar', 'damage-tesla-coil', 'forcefield')
MODES = ('joint', 'xyz', 'image', 'cue')
SCHEMA = 5
LESSON_VERSION = 1
LEGACY_TEST_IDS = {'ltz-test-green', 'ltz-test-purple'}


class ProgressStore(LevelResults, LinkedGames, EventStore, EconomyStore, BackupStore):
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
            version=db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0,4,SCHEMA):raise ValueError('Event progress requires the cleared player database')
            if version==4:
                if (db.execute('SELECT 1 FROM attempts LIMIT 1').fetchone() or db.execute('SELECT 1 FROM ledger LIMIT 1').fetchone()
                    or any(r[0] not in LEGACY_TEST_IDS for r in db.execute('SELECT id FROM players'))):
                    raise ValueError('Legacy player records remain; event upgrade requires the approved empty player base')
                db.execute('UPDATE game_selection SET game_id=NULL')
                for table in ('sessions','participants','saved_games','players','operations','ready_rosters','lesson_rosters'):
                    db.execute('DELETE FROM '+table)
                db.execute('DROP TABLE IF EXISTS shop_windows')
                db.execute('DELETE FROM economy_state');db.execute('DELETE FROM economy_catalogs')
            db.execute('CREATE TABLE IF NOT EXISTS game_events(id TEXT PRIMARY KEY,data TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS event_selection(id INTEGER PRIMARY KEY CHECK(id=1),event_id TEXT REFERENCES game_events(id))')
            db.execute('INSERT OR IGNORE INTO event_selection VALUES(1,NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS players(id TEXT PRIMARY KEY, data TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS sessions(side TEXT PRIMARY KEY CHECK(side IN (\'green\',\'purple\')), player_id TEXT UNIQUE REFERENCES players(id))')
            db.execute('CREATE TABLE IF NOT EXISTS attempts(id TEXT PRIMARY KEY, data TEXT NOT NULL)')
            db.execute("CREATE INDEX IF NOT EXISTS attempt_outcome ON attempts(json_extract(data,'$.outcome'))")
            db.execute("CREATE INDEX IF NOT EXISTS attempt_event ON attempts(json_extract(data,'$.event_id'))")
            db.execute('CREATE TABLE IF NOT EXISTS participants(run_id TEXT REFERENCES attempts(id), player_id TEXT REFERENCES players(id), PRIMARY KEY(run_id,player_id))')
            db.execute('CREATE TABLE IF NOT EXISTS ledger(id TEXT PRIMARY KEY, player_id TEXT REFERENCES players(id), amount INTEGER NOT NULL, data TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS operations(id TEXT PRIMARY KEY, data TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS ready_rosters(id TEXT PRIMARY KEY, data TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS lesson_rosters(id TEXT PRIMARY KEY, data TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value INTEGER NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS saved_games(id TEXT PRIMARY KEY, data TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS game_selection(id INTEGER PRIMARY KEY CHECK(id=1), game_id TEXT REFERENCES saved_games(id))')
            db.execute('INSERT OR IGNORE INTO game_selection VALUES(1,NULL)')
            db.execute("INSERT OR IGNORE INTO meta VALUES('revision',1)")
            initialize_economy(db)
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
        player['is_test'] = False
        return migrate_player(player)

    @staticmethod
    def _new_player(player_id, name, *, created_at=None):
        return {'id': player_id, 'name': name, 'created_at': time.time() if created_at is None else created_at,
                'revision': 1, 'is_test': False,
                'selected_control': 1, 'unlocked_control': 1, 'wins_by_tier': [0, 0, 0, 0],
                'current_control_tier': 1, 'progression_stage': 'playing',
                'lesson': {'version': LESSON_VERSION, 'complete': False}, 'calibration_milestone': None,
                'levels': {track: 1 for track in TRACKS}, 'credits': 0, 'lifetime_score': 0,
                'attempts': 0, 'wins': 0, 'lifetime_kills':0, 'lifetime_kill_credits':0,
                'lifetime_bonus_credits':0,'lifetime_credits_earned':0}

    def _put_player(self, db, player):
        player['revision'] += 1
        db.execute('UPDATE players SET data=? WHERE id=?', (encoded(player), player['id']))
        self._sync_game_player(db, player)

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

    def create_player(self, name, operation_id, *, side=None, event_id=None):
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 32 or any(ord(c) < 32 for c in name):
            raise ValueError('player name must contain 1–32 printable characters')
        intent = {'action': 'create', 'name': name.strip(), 'event_id':event_id}
        if side is not None:
            if side not in ('green', 'purple'):
                raise ValueError('invalid side')
            intent['side'] = side
        with self.transaction(write=True) as db:
            previous = self._operation(db, operation_id, intent)
            if previous is not None:
                return previous
            event=self._event(db,event_id)
            player = self._new_player(uuid.uuid4().hex, name.strip())
            player['event_id']=event['id']
            db.execute('INSERT INTO players VALUES(?,?)', (player['id'], encoded(player)))
            if side is not None:
                self._select_player(db, side, player['id'])
            result = {'player_id': player['id']}
            self._remember(db, operation_id, intent, result)
            self._touch(db)
            return result

    def select_player(self, side, player_id, event_id=None):
        if side not in ('green', 'purple'):
            raise ValueError('invalid side')
        with self.transaction(write=True) as db:
            self._event(db,event_id)
            self._select_player(db, side, player_id)
            self._touch(db)

    def _select_player(self, db, side, player_id):
        self._pair_selection_guard(db)
        current = db.execute('SELECT player_id FROM sessions WHERE side=?', (side,)).fetchone()
        if current:
            self._idle(db, current[0], changing_profile=True)
        if player_id:
            if self._player(db,player_id).get('event_id')!=self._event(db)['id']:raise ValueError('Player belongs to another event')
            self._idle(db, player_id, changing_profile=True)
            other = db.execute('SELECT side FROM sessions WHERE player_id=? AND side!=?', (player_id, side)).fetchone()
            if other:
                raise ValueError('player is selected on the other side; release them there first')
        db.execute('DELETE FROM sessions WHERE side=?', (side,))
        if player_id:
            db.execute('INSERT INTO sessions VALUES(?,?)', (side, player_id))
            # Choosing a name prepares a fresh game. Loading a linked save uses
            # its own atomic path and restores that game's control progression.
            self._fresh_player_controls(db, self._player(db, player_id))

    def mutate_player(self, side, data):
        raise ValueError('Upgrades are purchased automatically; controls follow the saved game level')

    def snapshot(self, side=None):
        with self.transaction() as db:
            events=self.events_snapshot(db)
            players = [json.loads(row[0]) for row in db.execute("SELECT data FROM players WHERE json_extract(data,'$.event_id')=? ORDER BY id",(events['active_id'],))]
            roster = {row['side']: row['player_id'] for row in db.execute('SELECT * FROM sessions')}
            by_id = {player['id']: player for player in players}
            active = [json.loads(row[0]) for row in db.execute("SELECT data FROM attempts WHERE json_extract(data,'$.outcome')='running'")]
            return {'revision': db.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0],
                    'events':events, 'saved_games': self.games_snapshot(db),
                    'players': [{'id': p['id'], 'name': p['name'], 'is_test': p['is_test']} for p in sorted(players, key=lambda p: (not p['is_test'], p['name'].casefold(), p['id']))],
                    'roster': {team: by_id[pid] for team, pid in roster.items()},
                    'player': by_id.get(roster.get(side)),
                    'shop':quote(db,by_id.get(roster.get(side))),
                    'latest_result':self.latest_result(db,roster.get(side)),
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

    def release_start_reservation(self, reservation_id):
        """Only undo an unconsumed Start lock; never release a calibration lock."""
        with self.transaction(write=True) as db:
            key=identifier(reservation_id)
            if not db.execute('SELECT 1 FROM ready_rosters WHERE id=?',(key,)).fetchone():return
            if db.execute("SELECT 1 FROM attempts WHERE json_extract(data,'$.outcome')='running' LIMIT 1").fetchone():
                raise ValueError('A match is active; its Start reservation cannot be released')
            db.execute('DELETE FROM ready_rosters WHERE id=?',(key,))
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
        if data.get('reward_enabled') is not True:
            raise ValueError('Every match must belong to an event and award earned progress')
        meta = data.get('metadata')
        if not isinstance(meta, dict) or len(encoded(meta)) > 100000:
            raise ValueError('invalid attempt metadata')
        if meta.get('reward_rules') is not None:validate_reward_rule(meta['reward_rules'])
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
            event=self._event(db,data.get('event_id'))
            reward_enabled=True
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
            if 'expected_game_id' in data and data['expected_game_id'] != (self._active_game(db) or {}).get('id'):
                raise ValueError('saved game changed while preparing the run; retry Start')
            game=self._active_game(db)
            if not game or set(game.get('atoms',{}))!={'green','purple'}:raise ValueError('Select one starting Atom for each player')
            if meta.get('contract_control_tier')!=game['level']:raise ValueError('Saved level changed; retry Start')
            for member in participants:
                if self._player(db,member['player_id'])['event_id']!=event['id']:raise ValueError('Player event mismatch')
                primary=game['atoms'][member['side']]['track']
                choices=('damage-machine-gun','damage-flamethrower') if member['side']=='green' else ('damage-mortar','damage-tesla-coil')
                member['eligible_tracks']=[primary]+([t for t in choices if t!=primary] if game['level']==4 else [])
            attempt = {'run_id': run_id, 'event_id':event['id'], 'assisted':game.get('assisted',False), 'started_at': time.time(), 'finished_at': None,
                       'game_id': self._lock_game_pair(db, participants),
                       'outcome': 'running', 'reward_enabled': reward_enabled, 'metadata': meta,
                       'requested_reward_enabled': True,
                       'wallet_at_start':{p['player_id']:self._player(db,p['player_id'])['credits'] for p in participants},
                       'catalog_revision':quote(db,None)['catalog_revision'],
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
            if outcome not in ('won', 'overrun', 'operator_ended', 'aborted', 'interrupted'):
                raise ValueError('invalid terminal outcome')
            finite(data.get('active_seconds'))
            finite(data.get('finished_at'))
            integer(data.get('released_orcs', 0))
            validate_heatmap(data.get('kill_heatmap'),kills)
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
            credit_total, bonus_total, reward = validate_reward(a,data,final)
            delta = kills - a['kills']
            credit_delta=credit_total-a.get('kill_credits',a['kills'])
            bonus_delta=bonus_total-a.get('bonus_credits',0)
            if credit_delta<0 or bonus_delta<0:raise ValueError('rewards must be cumulative')
            for participant in a['participants']:
                p = self._player(db, participant['player_id'])
                current_game_progress = self._result_game_progress(db, p, a.get('game_id'))
                if a['reward_enabled'] and (credit_delta or bonus_delta or delta):
                    p['credits'] += credit_delta+bonus_delta
                    p['lifetime_score'] += delta
                    p['lifetime_kills'] += delta
                    p['lifetime_kill_credits'] += credit_delta
                    p['lifetime_bonus_credits'] += bonus_delta
                    p['lifetime_credits_earned'] += credit_delta+bonus_delta
                    key = f'{run_id}:{sequence}:{p["id"]}'
                    db.execute('INSERT INTO ledger VALUES(?,?,?,?)', (key, p['id'], credit_delta, encoded({'kind': 'earned', 'run_id': run_id, 'kills':delta,'kill_credits':credit_delta,'at': time.time()})))
                    if bonus_delta:
                        db.execute('INSERT INTO ledger VALUES(?,?,?,?)',(f'{run_id}:bonus:{p["id"]}',p['id'],bonus_delta,encoded({'kind':'stack_bonus','run_id':run_id,'at':time.time()})))
                if final and a['reward_enabled']:
                    if not recovered_result:
                        p['attempts'] += 1
                    if outcome == 'won':
                        previous_tier = p['current_control_tier']
                        p['wins'] += 1
                        tier = participant['control_tier']
                        p['wins_by_tier'][tier - 1] += 1
                        if 'game_wins_by_tier' in p:
                            p['game_wins_by_tier'][tier - 1] += 1
                        if tier==previous_tier and (reward or {}).get('victory_method')=='center_stack':
                            self._advance_player(p,run_id,a)
                    if outcome in ('won','overrun','operator_ended'):
                        self.settle_upgrades(db,p,participant,a,forced=outcome=='operator_ended')
                if credit_delta or bonus_delta or delta or final:
                    self._put_result_player(db,p,a.get('game_id'),current_game_progress)
            if final and a.get('unlocks'):
                row=db.execute('SELECT data FROM saved_games WHERE id=?',(a['game_id'],)).fetchone()
                game=json.loads(row[0]);game['level']=max(a['unlocks'].values());self._write_game(db,game)
            a.update(kills=kills, sequence=sequence,kill_credits=credit_total,bonus_credits=bonus_total,reward=reward)
            if final:
                a['assisted']=bool(a.get('assisted') or outcome=='operator_ended' or (data.get('telemetry') or {}).get('operator_actions'))
                a.update(outcome=outcome, finished_at=data['finished_at'], result=data,
                         wallet_after_save={p['player_id']:self._player(db,p['player_id'])['credits'] for p in a['participants']})
                if outcome in ('won','overrun','operator_ended'):
                    a['statistics']=statistics_at_finish(a,event_attempts(db,a['event_id']))
            db.execute('UPDATE attempts SET data=? WHERE id=?', (encoded(a), run_id))
            self._touch(db)
            return a

    def recover(self):
        """Called by Game only AFTER its durable pending results have replayed."""
        with self.transaction() as db:
            unfinished = [json.loads(row[0]) for row in db.execute('SELECT data FROM attempts')]
        for a in unfinished:
            if a['outcome'] == 'running':
                if a['metadata'].get('reward_rules') and not a.get('reward'):
                    a['kill_credits']=0
                    a['reward']={'version':1,'revision':a['metadata']['reward_rules']['revision'],'sequence':0,'kill_credits':0,'counts':dict.fromkeys(('grunt','runner','breaker','brute'),0),'combat_kills':dict.fromkeys(('grunt','runner','breaker','brute'),0),'purge_kills':dict.fromkeys(('grunt','runner','breaker','brute'),0)}
                self.record({'run_id': a['run_id'], 'kills': a['kills'], 'sequence': a['sequence'] + 1,
                             'outcome': 'interrupted', 'active_seconds': 0, 'finished_at': time.time(), 'released_orcs': 0,
                             'recovery_interrupted': True, **({'reward':{**a['reward'],'stack_bonus':0,'total_earned':a['kill_credits'],'victory_method':None}} if a.get('reward') else {})}, final=True)

    def attempt(self, run_id):
        with self.transaction() as db:
            row=db.execute('SELECT data FROM attempts WHERE id=?',(identifier(run_id),)).fetchone()
            if row is None:raise ValueError('attempt not found')
            return json.loads(row[0])

    def history(self, player_id, query):
        with self.transaction() as db:
            event_id=self.events_snapshot(db)['active_id']
            if query.get('combined'):
                attempts = [json.loads(row[0]) for row in db.execute("SELECT data FROM attempts WHERE json_extract(data,'$.event_id')=?",(event_id,))]
            else:
                if self._player(db,player_id).get('event_id')!=event_id:raise ValueError('Player belongs to another event')
                attempts = [json.loads(row[0]) for row in db.execute('SELECT a.data FROM attempts a JOIN participants p ON a.id=p.run_id WHERE p.player_id=?', (player_id,))]
        rows = []
        for a in attempts:
            if a['outcome'] == 'running':
                continue
            if not a['participants']:
                continue
            p = next((p for p in a['participants'] if (p['side']==query['side_at_run'] if query.get('combined') and query.get('side_at_run') else p['player_id']==player_id)), a['participants'][0])
            meta = a['metadata']
            result = a['result'] or {}
            banked = banks_kill_credits(a)
            cohort = fingerprint({'metadata': {k: v for k, v in meta.items() if k not in ('settings_revision',)},
                                  'loadouts': [{k: p[k] for k in ('side', 'control_tier', 'levels')} for p in a['participants']]})
            row = {'event_id':a['event_id'],'assisted':bool(a.get('assisted') or a.get('manual_advance') or a['outcome']=='operator_ended'), 'manual_advance':a.get('manual_advance'), 'run_id': a['run_id'], 'finished_at': a['finished_at'], 'outcome': a['outcome'],
                   'score': a.get('kill_credits',a['kills']) if banked else 0, 'kills': a['kills'],
                   'kill_credits':a.get('kill_credits',a['kills']) if banked else 0,'bonus_credits':a.get('bonus_credits',0) if a['reward_enabled'] else 0,
                   'total_earned':(a.get('kill_credits',a['kills'])+a.get('bonus_credits',0)) if banked else 0,'reward':a.get('reward'),
                   'active_seconds': None if a['outcome'] == 'interrupted' else result.get('active_seconds'),
                   'control_tier': p['control_tier'], 'side': p['side'], 'levels': p['levels'],
                   'partner': ' + '.join(other['name'] for other in a['participants'] if other['player_id'] != player_id) or 'Solo',
                   'completion_awarded': a['reward_enabled'] and a['outcome'] == 'won',
                   'unlocked_control': a.get('unlocks', {}).get(player_id),
                   'released_orcs': result.get('released_orcs'),'kill_heatmap':result.get('kill_heatmap'),'telemetry':result.get('telemetry'), 'metadata': meta, 'cohort': cohort,
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
        comparable = len({r['cohort'] for r in rows}) == 1 and not any(r['assisted'] for r in rows)
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

    @staticmethod
    def latest_result(db, player_id):
        if not player_id:return None
        roster=[r[0] for r in db.execute('SELECT player_id FROM sessions')]
        partner=next((pid for pid in roster if pid!=player_id),None) if player_id in roster and len(roster)==2 else None
        row=db.execute("SELECT a.data FROM attempts a JOIN participants p ON p.run_id=a.id WHERE p.player_id=? AND json_extract(a.data,'$.outcome')!='running' AND (? IS NULL OR EXISTS(SELECT 1 FROM participants other WHERE other.run_id=a.id AND other.player_id=?)) ORDER BY json_extract(a.data,'$.finished_at') DESC,a.id DESC LIMIT 1",(player_id,partner,partner)).fetchone()
        if not row:return None
        a=json.loads(row[0]);r=a.get('reward') or {};result=a.get('result') or {}
        participant=next(p for p in a['participants'] if p['player_id']==player_id)
        eligible=a['reward_enabled'];credits=a.get('kill_credits',a['kills']) if banks_kill_credits(a) else 0;bonus=a.get('bonus_credits',0) if eligible else 0
        return {'run_id':a['run_id'],'outcome':a['outcome'],'saved':True,'event_id':a['event_id'],'purchases':a.get('purchases',{}).get(player_id,[]),'balance':a.get('wallet_after_save',{}).get(player_id),'manual_advance':a.get('manual_advance'),
                'kills':a['kills'],'kill_credits':credits,'stack_bonus':bonus,'total_earned':credits+bonus,
                'active_seconds':result.get('active_seconds'),'control_tier':participant['control_tier'],
                'victory_method':r.get('victory_method'),'core_health_at_stack':r.get('core_health_at_stack'),
                'counts':r.get('counts'),'values':a['metadata'].get('reward_rules',{}).get('values'),
                'statistics':result_view(db,a) if a['outcome'] in ('won','overrun','operator_ended') else None,
                'player_id':player_id,'side':participant['side'],
                'unlocked_control':a.get('unlocks',{}).get(player_id)}
