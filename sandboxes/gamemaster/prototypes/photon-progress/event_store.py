"""Event membership and operator progression, owned by Progress."""
import json
import time
import uuid
from ltz_records import encoded, identifier


class EventStore:
    @staticmethod
    def _event(db, expected=None):
        row = db.execute('SELECT e.data FROM game_events e JOIN event_selection s ON s.event_id=e.id WHERE s.id=1').fetchone()
        if not row:
            raise ValueError('Game Master must create or select an event first')
        event = json.loads(row[0])
        if expected is not None and expected != event['id']:
            raise ValueError('Event changed; refresh before continuing')
        return event

    @staticmethod
    def events_snapshot(db):
        selected = db.execute('SELECT event_id FROM event_selection WHERE id=1').fetchone()[0]
        rows = [json.loads(r[0]) for r in db.execute('SELECT data FROM game_events ORDER BY json_extract(data,\'$.created_at\') DESC,id')]
        return {'active_id': selected, 'active': next((e for e in rows if e['id']==selected), None), 'rows': rows}

    def event_preview(self, value):
        if not isinstance(value, dict) or value.get('action') not in ('create','select'):
            raise ValueError('Choose create or select event')
        identifier(value.get('operation_id'))
        if value['action']=='create':
            name=value.get('name')
            if not isinstance(name,str) or not 1<=len(name.strip())<=80 or any(ord(c)<32 for c in name):
                raise ValueError('Event name must contain 1–80 printable characters')
        with self.transaction() as db:
            self._games_idle(db)
            if value['action']=='select' and not db.execute('SELECT 1 FROM game_events WHERE id=?',(identifier(value.get('event_id')),)).fetchone():
                raise ValueError('Event not found')

    def event_command(self, value):
        self.event_preview(value)
        intent={k:value[k] for k in ('action','name','event_id') if k in value}
        with self.transaction(write=True) as db:
            old=self._operation(db,value['operation_id'],intent)
            if old is not None:return old
            self._games_idle(db)
            if value['action']=='create':
                event={'id':uuid.uuid4().hex,'name':value['name'].strip(),'created_at':time.time()}
                db.execute('INSERT INTO game_events VALUES(?,?)',(event['id'],encoded(event)))
            else:
                event=json.loads(db.execute('SELECT data FROM game_events WHERE id=?',(value['event_id'],)).fetchone()[0])
            db.execute('UPDATE game_selection SET game_id=NULL WHERE id=1')
            db.execute('DELETE FROM sessions')
            db.execute('UPDATE event_selection SET event_id=? WHERE id=1',(event['id'],))
            result={'event_id':event['id']}
            self._remember(db,value['operation_id'],intent,result);self._touch(db)
            return result

    @staticmethod
    def _advance_player(p, run_id, attempt):
        tier=p['current_control_tier']
        if tier>=4:return
        p.update(current_control_tier=tier+1, selected_control=tier+1, unlocked_control=tier+1)
        p['levels']['forcefield']=tier+1
        attempt.setdefault('unlocks',{})[p['id']]=tier+1
        if tier==2:
            p.update(progression_stage='calibration_pending',calibration_milestone=f'{run_id}:{p["id"]}')
            attempt.setdefault('calibration_milestones',{})[p['id']]=p['calibration_milestone']

    def advance_level(self, value):
        run_id=identifier(value.get('run_id'))
        with self.transaction(write=True) as db:
            event=self._event(db,value.get('event_id'))
            self._games_idle(db)
            a=self._attempt(db,run_id);game=self._active_game(db)
            if not game or a.get('game_id')!=game['id'] or a.get('event_id')!=event['id']:
                raise ValueError('Select the saved pair from this match before advancing')
            if a['outcome'] not in ('won','overrun','operator_ended'):
                raise ValueError('Finish a match before unlocking the next level')
            if a.get('unlocks') or a.get('manual_advance'):
                return a
            latest=db.execute("SELECT id FROM attempts WHERE json_extract(data,'$.game_id')=? ORDER BY json_extract(data,'$.started_at') DESC,id DESC LIMIT 1",(game['id'],)).fetchone()
            if not latest or latest[0]!=run_id:raise ValueError('Only the latest match can unlock the next level')
            if game['level']!=a['metadata']['contract_control_tier']:
                raise ValueError('This pair has already advanced beyond this match')
            for member in game['players'].values():
                p=self._player(db,member['player_id'])
                self._advance_player(p,run_id,a);self._put_player(db,p)
            game=self._active_game(db)
            game.update(level=min(4,game['level']+1),assisted=True)
            self._write_game(db,game)
            a['manual_advance']={'at':time.time(),'level':game['level'],'source':'gamemaster'}
            db.execute('UPDATE attempts SET data=? WHERE id=?',(encoded(a),run_id));self._touch(db)
            return a
