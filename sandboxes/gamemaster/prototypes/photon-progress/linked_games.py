"""Saved co-op progress. Wallets and purchases remain in their player ledger."""
import copy
import json
import time
import uuid
from ltz_records import encoded, identifier, integer, finite

SIDES = ('green', 'purple')
FIELDS = ('current_control_tier', 'selected_control', 'unlocked_control',
          'progression_stage', 'lesson', 'calibration_milestone', 'game_wins_by_tier')


def progression(player):
    value = {key: copy.deepcopy(player[key]) for key in FIELDS if key in player}
    value.setdefault('game_wins_by_tier', list(player['wins_by_tier']))
    return value


def validate(game):
    identifier(game['id']);identifier(game['event_id']);integer(game['level'],1,4)
    if not isinstance(game.get('atoms'),dict) or not set(game['atoms'])<=set(SIDES):raise ValueError('Invalid Atom bindings')
    tags=[]
    for side,atom in game['atoms'].items():
        integer(atom['tag'],0,999);tags.append(atom['tag'])
        tracks=('damage-machine-gun','damage-flamethrower') if side=='green' else ('damage-mortar','damage-tesla-coil')
        if atom.get('track') not in tracks or atom.get('source') not in ('camera','gamemaster'):raise ValueError('Invalid Atom assignment')
    if len(set(tags))!=len(tags):raise ValueError('Atom codes must be distinct')
    if (not isinstance(game.get('name'), str) or not 1 <= len(game['name'].strip()) <= 64
            or any(ord(c) < 32 for c in game['name'])):
        raise ValueError('game name must contain 1–64 characters')
    if type(game.get('locked')) is not bool or set(game.get('players', {})) != set(SIDES):
        raise ValueError('saved game requires a linked player pair')
    ids = []
    for row in game['players'].values():
        ids.append(identifier(row['player_id']))
        p = row['progression']
        tier = integer(p['current_control_tier'], 1, 4)
        if integer(p['selected_control'],1,4) != tier or integer(p['unlocked_control'],1,4) != tier:
            raise ValueError('invalid saved control tier')
        if p['progression_stage'] not in ('playing', 'calibration_pending') or type(p['lesson'].get('complete')) is not bool:
            raise ValueError('invalid saved calibration progress')
        if not isinstance(p['game_wins_by_tier'], list) or len(p['game_wins_by_tier']) != 4:
            raise ValueError('invalid saved game wins')
        for count in p['game_wins_by_tier']: integer(count)
    if len(set(ids)) != 2: raise ValueError('two distinct players required')
    finite(game['created_at']); finite(game['saved_at'])
    return game


class LinkedGames:
    def game_preview(self, value):
        if not isinstance(value, dict) or value.get('action') not in ('new', 'save', 'load', 'replay_level', 'replay_game'):
            raise ValueError('unknown saved game action')
        identifier(value.get('operation_id'))
        if 'name' in value and (not isinstance(value['name'], str) or not 1 <= len(value['name'].strip()) <= 64
                                or any(ord(c) < 32 for c in value['name'])):
            raise ValueError('game name must contain 1–64 printable characters')
        with self.transaction() as db:
            event=self._event(db,value.get('event_id'))
            if value['action'] in ('replay_level','replay_game'):
                intent={k:value[k] for k in ('action','game_id','name','event_id','run_id') if k in value}
                if self._operation(db,value['operation_id'],intent) is None:self._replay_source(db,value)
            if value['action'] == 'load':
                row = db.execute('SELECT data FROM saved_games WHERE id=?', (identifier(value.get('game_id')),)).fetchone()
                if not row: raise ValueError('saved game not found')
                game = validate(json.loads(row[0]))
                if game['event_id']!=event['id']:raise ValueError('Saved game belongs to another event')
                for member in game['players'].values(): self._player(db, member['player_id'])
            elif value['action'] == 'save' and db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0] != 2:
                raise ValueError('select both players before saving a game')

    def _replay_source(self, db, value):
        source=self._attempt(db,identifier(value.get('run_id')))
        game=self._active_game(db)
        pair=dict(db.execute('SELECT side,player_id FROM sessions'))
        latest=db.execute("SELECT id FROM attempts WHERE json_extract(data,'$.game_id')=? "
                          "ORDER BY json_extract(data,'$.started_at') DESC,id DESC LIMIT 1",
                          ((game or {}).get('id'),)).fetchone()
        if (not game or source['game_id']!=game['id'] or source['event_id']!=value.get('event_id')
                or source['outcome'] not in ('won','overrun','operator_ended','interrupted','aborted')
                or pair!={p['side']:p['player_id'] for p in source['participants']}
                or not latest or latest[0]!=source['run_id']):
            raise ValueError('Level result changed; refresh before replaying')
        return source

    @staticmethod
    def _active_game(db):
        row = db.execute('SELECT g.data FROM saved_games g JOIN game_selection s ON s.game_id=g.id WHERE s.id=1').fetchone()
        return json.loads(row[0]) if row else None

    @staticmethod
    def _write_game(db, game):
        validate(game)
        db.execute('INSERT OR REPLACE INTO saved_games VALUES(?,?)', (game['id'], encoded(game)))

    def _create_game(self, db, *, name=None, locked=False, activate=True):
        roster = dict(db.execute('SELECT side,player_id FROM sessions'))
        if set(roster) != set(SIDES): raise ValueError('select both players before saving or starting a game')
        players = {side: self._player(db, pid) for side, pid in roster.items()}
        event=self._event(db)
        if any(p.get('event_id')!=event['id'] for p in players.values()):raise ValueError('Pair event mismatch')
        game = {'event_id':event['id'],'level':1,'atoms':{},'assisted':False,'id': uuid.uuid4().hex, 'name': name or ' + '.join(players[s]['name'] for s in SIDES)[:64],
                'created_at': time.time(), 'saved_at': time.time(), 'locked': locked,
                'players': {s: {'player_id': p['id'], 'progression': progression(p)} for s, p in players.items()}}
        self._write_game(db, game)
        if activate: db.execute('UPDATE game_selection SET game_id=? WHERE id=1', (game['id'],))
        return game

    def _sync_game_player(self, db, player):
        game = self._active_game(db)
        if game:
            for row in game['players'].values():
                if row['player_id'] == player['id']:
                    row['progression'] = progression(player)
                    game['saved_at'] = time.time()
                    self._write_game(db, game)

    @staticmethod
    def _games_idle(db, *, saving=False):
        if db.execute("SELECT 1 FROM attempts WHERE json_extract(data,'$.outcome')='running' LIMIT 1").fetchone():
            raise ValueError('finish the current match before saving, loading or starting a new game')
        if db.execute('SELECT 1 FROM lesson_rosters LIMIT 1').fetchone() or not saving and db.execute('SELECT 1 FROM ready_rosters LIMIT 1').fetchone():
            raise ValueError('finish the shared ready/calibration transition first')

    def _fresh_player_controls(self, db, p):
        p.update(current_control_tier=1, selected_control=1, unlocked_control=1,
                 progression_stage='playing', lesson={'version': 1, 'complete': False},
                 calibration_milestone=None, game_wins_by_tier=[0, 0, 0, 0])
        p['levels']['forcefield']=1
        self._put_player(db, p)

    def _fresh_controls(self, db):
        for row in db.execute('SELECT player_id FROM sessions').fetchall():
            self._fresh_player_controls(db, self._player(db, row[0]))

    def prepare_game(self):
        """Default Start is a fresh L1 game unless a saved game is selected."""
        with self.transaction(write=True) as db:
            if self._active_game(db): return
            self._games_idle(db)
            if db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0] != 2:
                raise ValueError('select both Green and Purple players before Start')
            self._fresh_controls(db)
            self._create_game(db)
            self._touch(db)

    def game_command(self, value):
        self.game_preview(value)
        action = value.get('action')
        if action not in ('new', 'save', 'load', 'replay_level', 'replay_game'): raise ValueError('unknown saved game action')
        operation_id = identifier(value.get('operation_id'))
        intent = {k: value[k] for k in ('action', 'game_id', 'name','event_id','run_id') if k in value}
        with self.transaction(write=True) as db:
            self._event(db,value.get('event_id'))
            previous = self._operation(db, operation_id, intent)
            if previous is not None: return previous
            self._games_idle(db, saving=action=='save')
            game = self._active_game(db)
            if action in ('replay_level','replay_game'):
                source=self._replay_source(db,value)
                level=source['metadata']['contract_control_tier'] if action=='replay_level' else 1
                atoms=copy.deepcopy(game['atoms'])
                db.execute('UPDATE game_selection SET game_id=NULL WHERE id=1')
                for side,member in game['players'].items():
                    player=self._player(db,member['player_id'])
                    if action=='replay_game':self._fresh_player_controls(db,player)
                    else:
                        # A finished attempt proves this pair already passed its required lesson.
                        player.update(current_control_tier=level,selected_control=level,unlocked_control=level,
                                      progression_stage='playing',calibration_milestone=None)
                        player['levels']['forcefield']=level
                        self._put_player(db,player)
                replay=self._create_game(db,locked=True)
                replay.update(level=level,atoms=atoms,replayed_from=source['run_id'],assisted=game.get('assisted',False))
                self._write_game(db,replay)
                game=replay
            elif action == 'load':
                row = db.execute('SELECT data FROM saved_games WHERE id=?', (identifier(value.get('game_id')),)).fetchone()
                if not row: raise ValueError('saved game not found')
                game = validate(json.loads(row[0]))
                # Replace both sides in one transaction; individual selection cannot split the pair.
                for member in game['players'].values(): self._idle(db, member['player_id'], changing_profile=True)
                db.execute('UPDATE game_selection SET game_id=NULL WHERE id=1')
                db.execute('DELETE FROM sessions')
                for side, member in game['players'].items():
                    p = self._player(db, member['player_id'])
                    p.update(copy.deepcopy(member['progression']))
                    p['levels']['forcefield']=game['level']
                    self._put_player(db, p)
                    db.execute('INSERT INTO sessions VALUES(?,?)', (side, p['id']))
                db.execute('UPDATE game_selection SET game_id=? WHERE id=1', (game['id'],))
            elif action == 'new':
                db.execute('UPDATE game_selection SET game_id=NULL WHERE id=1')
                self._fresh_controls(db)
                game = self._create_game(db) if db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0] == 2 else None
            else:
                if game is None:
                    self._fresh_controls(db)
                    game = self._create_game(db, name=value.get('name'))
                if 'name' in value: game['name'] = value['name'].strip() if isinstance(value['name'], str) else ''
                game['saved_at'] = time.time()
                self._write_game(db, game)
            result = {'game_id': game['id'] if game else None, 'action': action}
            self._remember(db, operation_id, intent, result)
            self._touch(db)
            return result

    def _pair_selection_guard(self, db):
        game = self._active_game(db)
        if game and game['locked']:
            raise ValueError('this game’s player pair is locked; choose New game or Load game between matches')
        # Editing an unstarted saved roster prepares a different game, without overwriting its pair.
        if game: db.execute('UPDATE game_selection SET game_id=NULL WHERE id=1')

    def _lock_game_pair(self, db, participants):
        game = self._active_game(db)
        if game is None:raise ValueError('Saved event game is required')
        if {p['side']: p['player_id'] for p in participants} != {s: p['player_id'] for s, p in game['players'].items()}:
            raise ValueError('saved game players changed; reload the linked pair')
        game.update(locked=True, saved_at=time.time())
        self._write_game(db, game)
        return game['id']

    def games_snapshot(self, db):
        active = self._active_game(db)
        rows = []
        for row in db.execute("SELECT data FROM saved_games WHERE json_extract(data,'$.event_id')=? ORDER BY json_extract(data,'$.saved_at') DESC,id",(self.events_snapshot(db)['active_id'],)):
            game = json.loads(row[0])
            rows.append({k: game[k] for k in ('id', 'name', 'saved_at', 'locked','event_id','level','atoms','assisted')} | {
                'players': {s: {'id': m['player_id'], 'name': (p := self._player(db, m['player_id']))['name'],
                    'credits': p['credits'], 'levels': p['levels'], 'tier': m['progression']['current_control_tier']}
                    for s, m in game['players'].items()}})
        return {'active':active,'active_id': active['id'] if active else None, 'pair_locked': bool(active and active['locked']), 'rows': rows}

    def _result_game_progress(self, db, player, game_id):
        """Late durable results update their original game, never a newly loaded game."""
        current = progression(player)
        if game_id:
            row = db.execute('SELECT data FROM saved_games WHERE id=?', (game_id,)).fetchone()
            if not row: raise ValueError('result game is missing')
            game = json.loads(row[0])
            member = next(p for p in game['players'].values() if p['player_id'] == player['id'])
            player.update(copy.deepcopy(member['progression']))
        return current

    def _put_result_player(self, db, player, game_id, current):
        if game_id:
            game = json.loads(db.execute('SELECT data FROM saved_games WHERE id=?', (game_id,)).fetchone()[0])
            for member in game['players'].values():
                if member['player_id'] == player['id']: member['progression'] = progression(player)
            game['saved_at'] = time.time()
            self._write_game(db, game)
            if (self._active_game(db) or {}).get('id') != game_id:
                player.update(current)
                player['levels']['forcefield']=player['current_control_tier']
        self._put_player(db, player)

    def bind_atoms(self,value):
        with self.transaction(write=True) as db:
            self._event(db,value.get('event_id'));self._games_idle(db)
            game=self._active_game(db)
            if not game or game['id']!=value.get('game_id'):raise ValueError('Saved game changed')
            proposed=value.get('atoms')
            if not isinstance(proposed,dict) or set(proposed)!=set(SIDES):raise ValueError('One Atom per side is required')
            if game['atoms'] and game['atoms']!=proposed:raise ValueError('Starting Atoms are fixed for this saved game')
            game['atoms']=copy.deepcopy(proposed);validate(game)
            self._write_game(db,game);self._touch(db)
            return game
