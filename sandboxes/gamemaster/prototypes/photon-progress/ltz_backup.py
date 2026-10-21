"""Portable event backups with signed-wallet and membership validation."""
import json
import time
from ltz_records import encoded, integer, identifier, finite
from ltz_economy import TRACKS, catalog, state
from ltz_rewards import validate as validate_reward
from linked_games import validate as validate_game
from movement_results import validate_movement
from level_results import validate_statistics, validate_heatmap

SCHEMA=5
COLUMNS={'game_events':('id','data'),'players':('id','data'),'attempts':('id','data'),
         'participants':('run_id','player_id'),'ledger':('id','player_id','amount','data'),
         'operations':('id','data'),'economy_catalogs':('id','data'),'economy_state':('id','data'),
         'saved_games':('id','data')}


class BackupStore:
    def export(self):
        with self.transaction() as db:
            self._games_idle(db,saving=True)
            return {'schema_version':SCHEMA,'exported_at':time.time(),'tables':{
                t:[dict(r) for r in db.execute('SELECT * FROM '+t+' ORDER BY 1')] for t in COLUMNS}}

    def import_backup(self,backup,*,preview=False):
        if not isinstance(backup,dict) or type(backup.get('schema_version')) is not int or backup['schema_version']!=SCHEMA:
            raise ValueError('Only event-format backups are supported; legacy practice/global saves cannot be restored')
        tables=backup.get('tables')
        if not isinstance(tables,dict) or set(tables)!=set(COLUMNS) or len(encoded(backup))>20000000:raise ValueError('Invalid backup')
        for table,fields in COLUMNS.items():
            rows=tables[table]
            if not isinstance(rows,list) or len(rows)>100000:raise ValueError('Invalid backup rows')
            seen=set()
            for row in rows:
                if not isinstance(row,dict) or set(row)!=set(fields):raise ValueError('Invalid backup columns')
                keys=tuple(row[k] for k in fields[:2 if table=='participants' else 1])
                for k in keys:identifier(k)
                if keys in seen:raise ValueError('Duplicate backup record')
                seen.add(keys)
                if 'data' in row:
                    value=json.loads(row['data'])
                    if not isinstance(value,dict):raise ValueError('Invalid backup data')
                    encoded(value)
        with self.transaction(write=True) as db:
            self._games_idle(db)
            db.execute('SAVEPOINT imported')
            if not db.execute('SELECT 1 FROM game_events LIMIT 1').fetchone():
                db.execute('DELETE FROM economy_state');db.execute('DELETE FROM economy_catalogs')
            added=0
            for table,fields in COLUMNS.items():
                for row in tables[table]:
                    keys=fields[:2] if table=='participants' else fields[:1]
                    found=db.execute('SELECT * FROM '+table+' WHERE '+' AND '.join(k+'=?' for k in keys),tuple(row[k] for k in keys)).fetchone()
                    if found:
                        if dict(found)!=row:raise ValueError('Backup conflicts with '+table+':'+str(row[keys[0]]))
                    else:
                        db.execute('INSERT INTO '+table+' ('+','.join(fields)+') VALUES('+','.join('?' for _ in fields)+')',tuple(row[k] for k in fields));added+=1
            self._validate_event_backup(db)
            if preview:db.execute('ROLLBACK TO imported')
            else:self._touch(db)
            return {'new_records':added,'identical_records':sum(len(v) for v in tables.values())-added}

    def _validate_event_backup(self,db):
        if db.execute('PRAGMA foreign_key_check').fetchone():raise ValueError('Broken backup references')
        events={r[0]:json.loads(r[1]) for r in db.execute('SELECT * FROM game_events')}
        for key,event in events.items():
            if event.get('id')!=key or not isinstance(event.get('name'),str) or not 1<=len(event['name'].strip())<=80:raise ValueError('Invalid event')
            finite(event['created_at'])
        players={r[0]:json.loads(r[1]) for r in db.execute('SELECT * FROM players')}
        for key,p in players.items():
            if p.get('id')!=key or p.get('event_id') not in events or p.get('is_test') or key.startswith('ltz-test-'):raise ValueError('Invalid event player')
            if not isinstance(p.get('name'),str) or not 1<=len(p['name'].strip())<=32:raise ValueError('Invalid player name')
            integer(p['credits'],-1000000000);integer(p['revision'],1)
            if set(p['levels'])!=set(TRACKS)|{'forcefield'}:raise ValueError('Invalid upgrade tracks')
            for v in p['levels'].values():integer(v,1,4)
            tier=integer(p['current_control_tier'],1,4)
            if p['selected_control']!=tier or p['unlocked_control']!=tier or p['levels']['forcefield']!=tier:raise ValueError('Invalid control progression')
            if p['progression_stage'] not in ('playing','calibration_pending'):raise ValueError('Invalid calibration state')
            for k in ('lifetime_score','lifetime_kills','lifetime_kill_credits','lifetime_bonus_credits','lifetime_credits_earned','attempts','wins'):integer(p[k])
            rows=[dict(r) for r in db.execute('SELECT * FROM ledger WHERE player_id=?',(key,))]
            earned=bonus=kills=0
            for row in rows:
                entry=json.loads(row['data']);integer(row['amount'],-1000000000)
                if entry.get('kind') not in ('earned','stack_bonus','turret_upgrade'):raise ValueError('Unsupported ledger entry')
                if entry['kind']=='earned':earned+=row['amount'];kills+=integer(entry['kills'])
                if entry['kind']=='stack_bonus':bonus+=row['amount']
                if entry['kind'] in ('earned','stack_bonus') and row['amount']<0:raise ValueError('Negative earnings')
            if (sum(r['amount'] for r in rows),earned,bonus,kills)!=(p['credits'],p['lifetime_kill_credits'],p['lifetime_bonus_credits'],p['lifetime_kills']):raise ValueError('Wallet or score does not match ledger')
            if p['lifetime_score']!=kills or p['lifetime_credits_earned']!=earned+bonus:raise ValueError('Invalid earned score')
            for track in TRACKS:
                upgrades=[json.loads(r['data'])['level'] for r in rows if json.loads(r['data']).get('kind')=='turret_upgrade' and json.loads(r['data']).get('track')==track]
                if sorted(upgrades)!=list(range(2,p['levels'][track]+1)):raise ValueError('Turret tiers do not match purchase ledger')
        games={r[0]:validate_game(json.loads(r[1])) for r in db.execute('SELECT * FROM saved_games')}
        for key,g in games.items():
            if g['id']!=key or g['event_id'] not in events:raise ValueError('Invalid saved event game')
            for member in g['players'].values():
                if member['player_id'] not in players or players[member['player_id']]['event_id']!=g['event_id']:raise ValueError('Saved pair crosses events')
                if member['progression']['current_control_tier']!=g['level']:raise ValueError('Pair levels differ')
        for key,raw in db.execute('SELECT * FROM attempts'):
            a=json.loads(raw)
            if a.get('run_id')!=key or a.get('event_id') not in events or a.get('game_id') not in games or games[a['game_id']]['event_id']!=a['event_id']:raise ValueError('Invalid attempt membership')
            if a['outcome'] not in ('won','overrun','operator_ended','aborted','interrupted') or a.get('reward_enabled') is not True:raise ValueError('Invalid event outcome')
            if len(a['participants'])!=2 or {p['side'] for p in a['participants']}!={'green','purple'}:raise ValueError('Invalid event pair')
            members={p['player_id'] for p in a['participants']}
            if members!={p['player_id'] for p in games[a['game_id']]['players'].values()}:raise ValueError('Attempt pair differs from saved game')
            if members!={r[0] for r in db.execute('SELECT player_id FROM participants WHERE run_id=?',(key,))}:raise ValueError('Participant references differ')
            if any(pid not in players or players[pid]['event_id']!=a['event_id'] for pid in members):raise ValueError('Attempt crosses events')
            if a['result']['outcome']!=a['outcome'] or a['result']['kills']!=a['kills']:raise ValueError('Invalid saved result')
            credits,bonus,reward=validate_reward(a,a['result'],True)
            validate_statistics(a)
            validate_heatmap(a['result'].get('kill_heatmap'),a['kills'],a['result']['active_seconds'])
            validate_movement(a['result'].get('robot_movement'))
            if (credits,bonus,reward)!=(a.get('kill_credits'),a.get('bonus_credits',0),a.get('reward')):raise ValueError('Invalid reward evidence')
            costs=catalog(db,a['catalog_revision'])['prices']
            for member in a['participants']:
                tier=integer(member['control_tier'],1,4)
                binding=games[a['game_id']]['atoms'].get(member['side'])
                if not binding:raise ValueError('Missing starting Atom')
                primary=binding['track'];eligible=[primary]
                if tier==4:eligible += [t for t in (TRACKS[:2] if member['side']=='green' else TRACKS[2:]) if t!=primary]
                if member['eligible_tracks']!=eligible:raise ValueError('Invalid upgrade eligibility')
                ledger=[(amount,json.loads(raw)) for amount,raw in db.execute("SELECT amount,data FROM ledger WHERE player_id=? AND json_extract(data,'$.run_id')=?",(member['player_id'],key))]
                if sum(amount for amount,e in ledger if e['kind']=='earned')!=credits or sum(amount for amount,e in ledger if e['kind']=='stack_bonus')!=bonus:raise ValueError('Match earnings do not match ledger')
                receipts=a.get('purchases',{}).get(member['player_id'],[])
                if sorted(encoded(e) for _,e in ledger if e['kind']=='turret_upgrade')!=sorted(encoded(e) for e in receipts):raise ValueError('Missing upgrade ledger receipt')
                if a['outcome']=='operator_ended' and len(receipts)>1:raise ValueError('Duplicate forced upgrade')
                for receipt in receipts:
                    if receipt['track'] not in member['eligible_tracks'] or costs[receipt['track']][str(receipt['level'])]!=receipt['price']:raise ValueError('Invalid upgrade receipt')
        for row in db.execute('SELECT player_id,amount,data FROM ledger'):
            entry=json.loads(row['data']);a=self._attempt(db,identifier(entry.get('run_id')))
            if row['player_id'] not in {p['player_id'] for p in a['participants']}:raise ValueError('Ledger recipient mismatch')
            if entry['kind']=='turret_upgrade' and (entry not in a.get('purchases',{}).get(row['player_id'],[]) or row['amount']!=-entry['price']):raise ValueError('Invalid purchase ledger')
        s=state(db);catalog(db,s['active'])
