"""Progress-owned prices and automatic purchases in the result transaction."""
import json
import time

TRACKS = ('damage-machine-gun', 'damage-flamethrower', 'damage-mortar', 'damage-tesla-coil')
DEFAULT_PRICES = {t: {str(l): 500*(l-1) for l in range(2,5)} for t in TRACKS}

def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)

def prices(value):
    if not isinstance(value, dict) or set(value) != set(TRACKS):
        raise ValueError('provide all four turret tracks')
    for levels in value.values():
        if not isinstance(levels, dict) or set(levels) != {'2', '3', '4'}:
            raise ValueError('provide all twelve T2–T4 prices')
        if any(type(v) is not int or not 0 <= v <= 100000 for v in levels.values()):
            raise ValueError('prices must be integer credits from 0 to 100000')
    return json.loads(encode(value))

def initialize(db):
    db.execute('CREATE TABLE IF NOT EXISTS economy_catalogs(id TEXT PRIMARY KEY, data TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS economy_state(id TEXT PRIMARY KEY, data TEXT NOT NULL)')
    db.execute('INSERT OR IGNORE INTO economy_catalogs VALUES(?,?)', ('catalog:1', encode({'revision':1,'prices':DEFAULT_PRICES})))
    db.execute('INSERT OR IGNORE INTO economy_state VALUES(?,?)', ('catalog', encode({'revision':1,'active':1,'pending':None})))

def state(db):
    row = db.execute("SELECT data FROM economy_state WHERE id='catalog'").fetchone()
    if not row:
        raise ValueError('price catalog unavailable')
    value = json.loads(row[0])
    if any(type(value.get(k)) is not int or value[k] < 1 for k in ('revision','active')):
        raise ValueError('invalid price catalog state')
    if s_pending:=value.get('pending'):
        if type(s_pending) is not int or not 1<=s_pending<=value['revision']:raise ValueError('invalid pending catalog')
    elif value.get('pending') is not None:raise ValueError('invalid pending catalog')
    if value['active']>value['revision']:raise ValueError('invalid active catalog')
    return value

def catalog(db, revision):
    row = db.execute('SELECT data FROM economy_catalogs WHERE id=?', (f'catalog:{revision}',)).fetchone()
    if not row:
        raise ValueError('price catalog unavailable; refresh before buying')
    value = json.loads(row[0]); prices(value['prices'])
    if type(value['revision']) is not int or value['revision'] != revision:
        raise ValueError('invalid price catalog revision')
    return value

def put_state(db, value):
    db.execute("UPDATE economy_state SET data=? WHERE id='catalog'", (encode(value),))

def quote(db, player):
    c=catalog(db,state(db)['active'])
    row=db.execute('SELECT g.data FROM saved_games g JOIN game_selection s ON s.game_id=g.id WHERE s.id=1').fetchone()
    game=json.loads(row[0]) if row else None
    eligible=[]
    if player and game:
        side=next((side for side,m in game['players'].items() if m['player_id']==player['id']),None)
        if side in game.get('atoms',{}):
            primary=game['atoms'][side]['track'];eligible=[primary]
            if game['level']==4:eligible += [t for t in (TRACKS[:2] if side=='green' else TRACKS[2:]) if t!=primary]
    return {'eligible_tracks':eligible,'contract':'photon.progress.shop','version':1,'status':'ready',
            'catalog_revision':c['revision'],'prices':c['prices'],'cards':[],
            'read_only':True,'total_cost':sum(sum(v.values()) for v in c['prices'].values())}


class EconomyStore:
    def economy_snapshot(self):
        with self.transaction() as db:
            s=state(db)
            return {'contract':'photon.progress.economy','version':1,'status':'ready',**s,
                    'catalog':catalog(db,s['active']),'pending_catalog':None}

    def save_prices(self,value):
        clean=prices(value.get('prices'))
        intent={'action':'prices','prices':clean,'revision':value.get('revision')}
        with self.transaction(write=True) as db:
            old=self._operation(db,value.get('operation_id'),intent)
            if old is not None:return old
            self._games_idle(db)
            s=state(db)
            if value.get('revision')!=s['revision']:raise ValueError('Prices changed; refresh first')
            revision=s['revision']+1
            db.execute('INSERT INTO economy_catalogs VALUES(?,?)',(f'catalog:{revision}',encode({'revision':revision,'prices':clean})))
            s.update(revision=revision,active=revision,pending=None);put_state(db,s)
            result={'revision':revision,'staged':False}
            self._remember(db,value['operation_id'],intent,result);self._touch(db)
            return result

    def settle_upgrades(self,db,player,participant,attempt,*,forced=False):
        costs=catalog(db,attempt['catalog_revision'])['prices']
        tracks=participant['eligible_tracks']
        receipts=[]
        while True:
            available=[t for t in tracks if player['levels'][t]<4]
            if not available:break
            track=min(available,key=lambda t:(player['levels'][t],tracks.index(t)))
            level=player['levels'][track]+1;cost=costs[track][str(level)]
            if not forced and player['credits']<cost:break
            player['credits']-=cost;player['levels'][track]=level
            receipt={'track':track,'level':level,'price':cost,'balance':player['credits'],
                     'forced':forced,'event_id':attempt['event_id'],'run_id':attempt['run_id'],
                     'catalog_revision':attempt['catalog_revision'],'kind':'turret_upgrade','at':time.time()}
            key=f"{attempt['run_id']}:upgrade:{player['id']}:{track}:{level}"
            db.execute('INSERT INTO ledger VALUES(?,?,?,?)',(key,player['id'],-cost,encode(receipt)))
            receipts.append(receipt)
            if forced:break
        attempt.setdefault('purchases',{})[player['id']]=receipts
