"""Game-owned breaker combat. No renderer, persistence, or sibling access."""
import math

COMBAT_VERSION = 1
DEFAULTS = {
    'breaker_attack_mode': 'melee',
    'breaker_range': 220.0,
    'breaker_draw_s': .5,
    'breaker_interval_s': 1.5,
    'breaker_tower_damage': 12.0,
    'breaker_core_damage': 12.0,
    'breaker_arrow_speed': 420.0,
}
RULES = {
    'breaker_range': (float, 50, 450),
    'breaker_draw_s': (float, .2, 1.5),
    'breaker_interval_s': (float, .75, 6),
    'breaker_tower_damage': (float, 0, 250),
    'breaker_core_damage': (float, 0, 250),
    'breaker_arrow_speed': (float, 200, 1200),
}
TYPES = ('grunt', 'runner', 'breaker', 'brute')


def blank_counts():
    return dict.fromkeys(TYPES, 0)


def segment_hit(a, b, c, d):
    """First segment intersection parameter, including collinear contact."""
    rx, ry = b[0]-a[0], b[1]-a[1]
    sx, sy = d[0]-c[0], d[1]-c[1]
    qx, qy = c[0]-a[0], c[1]-a[1]
    cross = rx*sy-ry*sx
    if abs(cross) > 1e-9:
        t, u = (qx*sy-qy*sx)/cross, (qx*ry-qy*rx)/cross
        return max(0., min(1., t)) if -1e-9 <= t <= 1+1e-9 and -1e-9 <= u <= 1+1e-9 else None
    if abs(qx*ry-qy*rx) > 1e-8:
        return None
    norm = rx*rx+ry*ry
    if norm < 1e-12:
        return None
    ends = sorted(((qx*rx+qy*ry)/norm, ((d[0]-a[0])*rx+(d[1]-a[1])*ry)/norm))
    return max(0., ends[0]) if ends[1] >= 0 and ends[0] <= 1 else None


class RangedCombat:
    def __init__(self, engine, core_planes):
        self.e, self.core_planes = engine, core_planes
        self.arrows, self.impacts = [], []
        self.next_id = 1
        self.targets, self.blockers = {}, []
        self.stats = dict.fromkeys(('shots', 'hits', 'blocks', 'misses', 'cancelled_draws',
                                   'deaths_before_release', 'tower_damage', 'core_damage',
                                   'tower_destructions', 'core_destructions', 'stopped_s', 'aim_s'), 0)
        self.counts = {key: blank_counts() for key in ('scheduled', 'released', 'killed', 'combat_kills', 'purge_kills')}
        engine.telemetry['enemy_counts'] = self.counts
        engine.telemetry['breaker_combat'] = {'version': COMBAT_VERSION, 'stats': self.stats}

    def start(self, schedule):
        self.e.telemetry['breaker_combat']['mode'] = self.e.settings['breaker_attack_mode']
        for number, (wave, counts) in enumerate(zip(self.e.wave_source, schedule['groups']), 1):
            offset = 0
            for group, count in zip(wave['groups'], counts):
                brute = ((offset+count)//41-offset//41) if number >= self.e.settings['brute_first_wave'] else 0
                kind = 'grunt' if group['enemy'] == 'brute' else group['enemy']
                self.counts['scheduled'][kind] += count-brute
                self.counts['scheduled']['brute'] += brute
                offset += count

    def enabled(self, enemy):
        return enemy.get('enemy_type') == 'breaker' and self.e.settings['breaker_attack_mode'] == 'ranged'

    def holding(self, enemy):
        return self.enabled(enemy) and enemy.get('combat_state') in ('aim', 'recover')

    def spawned(self, enemy):
        self.counts['released'][enemy['enemy_type']] += 1
        if self.enabled(enemy):
            enemy.update(combat_state='move', combat_started_at=self.e.sim_time,
                         next_scan_at=self.e.sim_time+(enemy['id'] % 4)*.05,
                         next_shot_at=self.e.sim_time, ranged_target=None, last_shot_at=None)

    def killed(self, enemy):
        kind = enemy['enemy_type']
        self.counts['killed'][kind] += 1
        self.counts['purge_kills' if enemy.get('death_cause') == 'core_purge' else 'combat_kills'][kind] += 1
        if self.enabled(enemy) and enemy.get('combat_state') == 'aim':
            self.stats['deaths_before_release'] += 1

    def geometry(self):
        e = self.e
        self.targets = {}
        for tower in e.combat_towers():
            sid = tower["socket_id"]
            if (tower.get('destroyed') or tower.get('deactivated')) or tower.get('hp', 0) <= 0:
                continue
            for pod, body in [('primary', tower), ('companion', tower.get('companion'))]:
                if body is None:
                    continue
                key = f'{sid}:{pod}'
                self.targets[key] = dict(key=key, kind='tower', socket_id=sid,
                    instance=tower.get('aim_instance'), x=body['x'], y=body['y'],
                    radius=body.get('pod_size', 112)/2)
        self.targets['core'] = dict(key='core', kind='core', x=e.level.core['x'], y=e.level.core['y'], instance='core')
        self.blockers = [(r['ax'], r['ay'], r['bx'], r['by']) for r in e._active_rows]
        self.blockers += [(f['ax'], f['ay'], f['bx'], f['by']) for f in e.force_fields.values() if e._field_operational(f)]
        self.blockers = [(ax,ay,bx,by,min(ax,bx)-1e-8,max(ax,bx)+1e-8,min(ay,by)-1e-8,max(ay,by)+1e-8) for ax,ay,bx,by in self.blockers]

    def endpoint(self, origin, target):
        dx, dy = origin[0]-target['x'], origin[1]-target['y']
        distance = math.hypot(dx, dy)
        if target['kind'] == 'core':
            # Intersection with the existing core octagon's half planes.
            ratio = min((limit/(nx*dx+ny*dy) for nx, ny, limit in self.core_planes
                         if nx*dx+ny*dy > 0), default=0)
            ratio = min(1., ratio)
        else:
            ratio = min(1., target['radius']/distance) if distance else 0
        return target['x']+dx*ratio, target['y']+dy*ratio

    def blocked(self, origin, end):
        first = None
        left,right=sorted((origin[0],end[0]));top,bottom=sorted((origin[1],end[1]))
        for ax, ay, bx, by, bl, br, bt, bb in self.blockers:
            if right<bl or left>br or bottom<bt or top>bb:continue
            t = segment_hit(origin, end, (ax, ay), (bx, by))
            if t is not None and (first is None or t < first):
                first = t
        return first

    def valid(self, enemy, target, retained=False):
        if target is None:
            return False
        distance = math.hypot(target['x']-enemy['x'], target['y']-enemy['y'])
        if distance > self.e.settings['breaker_range']*(1.1 if retained else 1):
            return False
        origin = (enemy['x'], enemy['y'])
        return self.blocked(origin, self.endpoint(origin, target)) is None

    def select(self, enemy):
        ordered = sorted(self.targets.values(), key=lambda t: (t['kind'] == 'core',
            (t['x']-enemy['x'])**2+(t['y']-enemy['y'])**2, t['key']))
        return next((t for t in ordered if self.valid(enemy, t)), None)

    def cancel(self, enemy):
        if enemy.get('combat_state') == 'aim':
            self.stats['cancelled_draws'] += 1
        enemy.update(combat_state='move', ranged_target=None, combat_started_at=self.e.sim_time)

    def aim(self, enemy, target):
        now = self.e.sim_time
        enemy.update(combat_state='aim', ranged_target=dict(target), combat_started_at=now,
                     release_at=max(now+self.e.settings['breaker_draw_s'], enemy.get('next_shot_at', now)))

    def face(self, enemy, target):
        dx, dy = target['x']-enemy['x'], target['y']-enemy['y']
        length = math.hypot(dx, dy)
        if length > 1e-9:
            enemy['facing_x'], enemy['facing_y'] = dx/length, dy/length
        enemy['vx'] = enemy['vy'] = 0.

    def prepare(self, living, dt):
        self.geometry()
        if self.e.core_stage == 'detonating':
            self.clear()
            return
        now = self.e.sim_time
        for enemy in living:
            if not self.enabled(enemy):
                continue
            selected = enemy.get('ranged_target')
            target = self.targets.get(selected['key']) if selected else None
            if selected and (not target or selected['instance'] != target['instance'] or not self.valid(enemy, target, True)):
                self.cancel(enemy)
                enemy['next_scan_at'] = now
            # A newly exposed tower takes precedence over the core; otherwise
            # retain a valid tower to avoid jitter between nearby defense pods.
            if (enemy.get('ranged_target') or {}).get('kind') == 'core' and now+1e-9 >= enemy.get('next_scan_at', 0):
                candidate = self.select(enemy)
                enemy['next_scan_at'] = now+.2
                if candidate and candidate['kind'] == 'tower':
                    self.cancel(enemy)
                    self.aim(enemy, candidate)
            if not enemy.get('ranged_target') and now+1e-9 >= enemy.get('next_scan_at', 0):
                target = self.select(enemy)
                enemy['next_scan_at'] = now+.2
                if target:
                    self.aim(enemy, target)
            if self.holding(enemy):
                target = self.targets[enemy['ranged_target']['key']]
                self.face(enemy, target)
                self.stats['stopped_s'] += dt
                if enemy['combat_state'] == 'recover' and now+1e-9 >= enemy['next_shot_at']-self.e.settings['breaker_draw_s']:
                    self.aim(enemy, target)
                if enemy['combat_state'] == 'aim':
                    self.stats['aim_s'] += dt

    def fire(self, living):
        if self.e.core_stage == 'detonating':
            return
        for enemy in living:
            if not self.holding(enemy):
                continue
            target = self.targets.get(enemy['ranged_target']['key'])
            if not self.valid(enemy, target, True):
                self.cancel(enemy)
                continue
            self.face(enemy, target)  # collision separation must not change bow facing
            if enemy['combat_state'] != 'aim' or self.e.sim_time+1e-9 < enemy['release_at']:
                continue
            now, settings = self.e.sim_time, self.e.settings
            origin = (enemy['x'], enemy['y'])
            end = self.endpoint(origin, target)
            duration = max(.001, math.dist(origin, end)/settings['breaker_arrow_speed'])
            damage = settings['breaker_'+target['kind']+'_damage']*settings['enemy_'+target['kind']+'_damage_multiplier']
            self.arrows.append(dict(id=self.next_id, enemy_id=enemy['id'], target=dict(target),
                origin_x=origin[0], origin_y=origin[1], target_x=end[0], target_y=end[1],
                launch_at=now, impact_at=now+duration, damage=damage, progress=0.))
            self.next_id += 1
            self.stats['shots'] += 1
            enemy.update(combat_state='recover', combat_started_at=now, last_shot_at=now,
                         next_shot_at=now+settings['breaker_interval_s'])

    def advance_arrows(self):
        e = self.e
        self.impacts = [i for i in self.impacts if e.sim_time-i['at'] <= .35][-128:]
        if e.core_stage == 'detonating':
            self.clear()
            return
        if not self.arrows:
            return
        self.geometry()
        remaining = []
        for arrow in self.arrows:
            old = arrow['progress']
            progress = min(1., max(0., (e.sim_time-arrow['launch_at'])/(arrow['impact_at']-arrow['launch_at'])))
            dx, dy = arrow['target_x']-arrow['origin_x'], arrow['target_y']-arrow['origin_y']
            a = arrow['origin_x']+old*dx, arrow['origin_y']+old*dy
            b = arrow['origin_x']+progress*dx, arrow['origin_y']+progress*dy
            blocked = self.blocked(a, b)
            if blocked is not None:
                self.stats['blocks'] += 1
                self.impacts.append(dict(id=arrow['id'], kind='blocked', at=e.sim_time,
                    x=a[0]+(b[0]-a[0])*blocked, y=a[1]+(b[1]-a[1])*blocked))
                continue
            arrow['progress'] = progress
            if progress < 1:
                remaining.append(arrow)
                continue
            target, damage = arrow['target'], arrow['damage']
            if target['kind'] == 'core':
                actual = min(max(0., e.core_hp), damage)
                was_alive = e.core_hp > 0
                e.core_hp = max(0., e.core_hp-damage)
                self.stats['core_damage'] += actual
                self.stats['core_destructions'] += int(was_alive and e.core_hp <= 0)
            else:
                tower = e.combat_tower(target['socket_id'])
                body = self.targets.get(target['key'])
                if not tower or (tower.get('destroyed') or tower.get('deactivated')) or not body or body['instance'] != target['instance']:
                    self.stats['misses'] += 1
                    continue
                actual = min(tower['hp'], damage)
                died = e._apply_tower_damage(tower, damage)
                self.stats['tower_damage'] += actual
                self.stats['tower_destructions'] += int(died)
                if died:
                    e._after_tower_destruction()
                    self.geometry()  # subsequent arrows see the now-broken shield
            self.stats['hits'] += 1
            self.impacts.append(dict(id=arrow['id'], kind='hit', at=e.sim_time, x=b[0], y=b[1]))
        self.arrows = remaining
        self.impacts = self.impacts[-128:]

    def clear(self):
        self.arrows.clear()
        for enemy in self.e.enemies.values():
            if self.enabled(enemy):
                self.cancel(enemy)

    def public_enemy(self, enemy):
        if not self.enabled(enemy):
            return {}
        return {'combat': {'variant': 'archer', 'state': enemy.get('combat_state', 'move'),
            'started_at': enemy.get('combat_started_at', 0), 'release_at': enemy.get('release_at'),
            'last_shot_at': enemy.get('last_shot_at'), 'next_shot_at': enemy.get('next_shot_at')}}

    def snapshot(self):
        return {'enemy_combat': {'contract': 'photon.enemy-combat', 'version': COMBAT_VERSION,
                'breaker_mode': self.e.settings['breaker_attack_mode']},
            'enemy_arrows': [{k: a[k] for k in ('id', 'enemy_id', 'origin_x', 'origin_y',
                'target_x', 'target_y', 'launch_at', 'impact_at')} for a in self.arrows],
            'enemy_arrow_impacts': [dict(i) for i in self.impacts]}
