"""One-use home defenses. They never enter socket topology or Atom placement."""
import math


def validate(raw, width, height):
    if raw is None or isinstance(raw, list) and not raw:
        return []
    if not isinstance(raw, list) or len(raw) != 4:
        raise ValueError('Atom home contract requires four positions')
    keys = set()
    for h in raw:
        if not isinstance(h, dict) or h.get('owner') not in ('green', 'purple') or type(h.get('slot')) is not int or h['slot'] not in (0, 1):
            raise ValueError('Invalid Atom home owner/slot')
        key = (h['owner'], h['slot'])
        if key in keys:
            raise ValueError('Duplicate Atom home')
        keys.add(key)
        for k in ('x', 'y', 'size', 'turret_x', 'turret_y', 'pod_size'):
            if type(h.get(k)) not in (int, float) or not math.isfinite(h[k]):
                raise ValueError('Invalid Atom home geometry')
        for x, y, size in ((h['x'], h['y'], h['size']), (h['turret_x'], h['turret_y'], h['pod_size'])):
            if not 48 <= size <= 112 or not size/2 <= x <= width-size/2 or not size/2 <= y <= height-size/2:
                raise ValueError('Atom home outside playfield')
    return [dict(h) for h in raw]


def platforms(game, saved=None):
    saved = saved if saved is not None else game.event_game
    tier = saved['level'] if saved else game.virtual_test_control or game.contract_control_tier
    result = []
    for h in game.level.atom_homes:
        codes = [tag for tag, side in game.atom_owners.items() if side == h['owner']]
        selected = (saved or {}).get('atoms', {}).get(h['owner'], {}).get('tag', codes[0])
        if selected not in codes:
            raise ValueError('Saved starting Atom does not match the configured team')
        ordered = [selected, next(code for code in codes if code != selected)]
        if h['slot'] and tier < 4:
            continue
        tag = ordered[h['slot']]
        result.append({**h, 'id': f"starter_{h['owner']}_{h['slot']+1}",
                       'atom_tag_id': tag, 'tower_type': game.piece_roles[tag]})
    return result


def make_tower(game, home, *, level=None, preview=False):
    tower = game._new_tower(home['atom_tag_id'], home['id'], home['tower_type'], home['owner'],
                            'starter', home=home, upgrade_level=level)
    # Already deployed at Start; it needs no Atom activation and cannot respawn.
    tower.update(activation_started_at=-3.0, activation_complete_at=0.0,
                 preview=preview, aim_instance=f"preview:{home['id']}:{home['atom_tag_id']}" if preview else tower['aim_instance'])
    return tower


def deploy(game):
    for home in platforms(game):
        if home['id'] not in game.starter_turrets:
            game.starter_turrets[home['id']] = make_tower(game, home)
        if game.virtual_play and home['atom_tag_id'] not in game.atom_presence:
            game.mobile_arms[home['owner']].tags[home['atom_tag_id']] = {k: home[k] for k in ('x', 'y')}


def preview(game, saved=None, teams=None):
    if not (saved or {}).get('atoms') and game.setup_starting_atoms:
        saved = {**(saved or {}), 'level': (saved or {}).get('level', game.virtual_test_control or 1),
                 'atoms': {side: {'tag': tag} for side, tag in game.setup_starting_atoms.items() if tag is not None}}
    homes = platforms(game, saved)
    towers = []
    for home in homes:
        track = 'damage-' + home['tower_type'].replace('_', '-')
        level = (teams or {}).get(home['owner'], {}).get('levels', {}).get(track, 1)
        if game.virtual_test_loadout is not None:
            level = max(1, game.virtual_test_loadout[track])
        tower = make_tower(game, home, level=level, preview=True)
        towers.append(game._public_tower(tower))
    return {'home_platforms': homes, 'starter_turrets': towers}
