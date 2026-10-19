"""Game-owned operator occupancy and activation; never commands robot hardware."""
import time
from . import event_rules


def reset(game):
    game.manual_atom_presence = {}
    game.physical_atom_presence = {}
    game.turret_states = {}


def activated(game, socket_id, team):
    game.turret_states[socket_id] = team


def reconcile_physical(game):
    """A confirmed Atom consumes conflicting manual choices permanently."""
    game.physical_atom_presence = dict(game.atom_presence)
    physical_sockets = set(game.physical_atom_presence.values())
    game.manual_atom_presence = {
        tag: sid for tag, sid in game.manual_atom_presence.items()
        if tag not in game.physical_atom_presence and sid not in physical_sockets
    }
    game.atom_presence.update(game.manual_atom_presence)


def validate_target(game, socket_id):
    if not isinstance(socket_id, str) or socket_id not in game.level.sockets:
        raise ValueError('Unknown turret socket')
    if game.phase not in ('setup', 'running'):
        raise ValueError('Reset before changing turrets in a finished game')


def validate_weapon(game, atom_id):
    event_rules.require_atom(game,atom_id)
    kind = game.piece_roles[atom_id]
    track = 'damage-' + kind.replace('_', '-')
    if game.virtual_test_loadout is not None and game.virtual_test_loadout[track] == 0:
        raise ValueError(f'{kind.replace("_", " ")} is locked in the practice loadout')


def select_atom(game, socket_id, atom_id):
    validate_target(game, socket_id)
    if atom_id is not None and (type(atom_id) is not int or atom_id not in game.atom_owners):
        raise ValueError('Select a configured Atom ID')
    if atom_id is not None and game.atom_visits.get(atom_id,{}).get('socket_id')==socket_id and game.atom_visits[atom_id].get('operator_pending') and not game.placements.get(socket_id,{}).get('destroyed'):
        return
    physical = game.physical_atom_presence if not game.virtual_play else {}
    if socket_id in physical.values() or atom_id in physical:
        raise ValueError('Physical Atom detection takes priority; move the physical Atom first')
    tower = game.placements.get(socket_id)
    if atom_id is not None:
        event_rules.require_atom(game,atom_id)
        if tower is None:
            validate_weapon(game, atom_id)  # Reject before changing occupancy.
    for tag, visit in game.atom_visits.items():
        if atom_id is None and visit.get('socket_id')==socket_id and visit.pop('operator_pending',False):
            visit['departed']=True
    for tag, sid in game.atom_presence.items():
        visit = game.atom_visits.get(tag)
        if (tag == atom_id or sid == socket_id) and visit and visit['socket_id'] == sid:
            visit['departed'] = True
    # An Atom and a target can each have only one effective association.
    game.manual_atom_presence = {
        tag: sid for tag, sid in game.manual_atom_presence.items()
        if tag != atom_id and sid != socket_id
    }
    game.atom_presence = {
        tag: sid for tag, sid in game.atom_presence.items()
        if tag != atom_id and sid != socket_id
    }
    if atom_id is not None:
        # A manual activation never grants an occupancy buff. Identical retries
        # are consumed until an explicit clear, move or observed departure.
        set_activation(game, socket_id, game.atom_owners[atom_id], new_visit=True, atom_id=atom_id)
        game.atom_visits[atom_id] = {
            'socket_id': socket_id, 'departed': False, 'operator_pending':True,
            'accepted_at': max(game._physical_sampled_at, time.time()),
        }
    game._event('operator_atom_selected', socket_id=socket_id, atom_tag_id=atom_id)


def set_activation(game, socket_id, state, *, new_visit=False, atom_id=None):
    validate_target(game, socket_id)
    if state not in ('green', 'purple', 'deactivated'):
        raise ValueError('Turret activation must be green, purple or deactivated')
    tower = game.placements.get(socket_id)
    if state == 'deactivated':
        if tower and not tower.get('destroyed'):
            # X uses the normal destruction path (zero HP, effects and topology),
            # including turrets disabled by an older operator client.
            tower['deactivated'] = False
            if game._apply_tower_damage(tower, max(1.0, float(tower['hp']))):
                game._after_tower_destruction()
        game.turret_states[socket_id] = state
    else:
        if not new_visit and tower and not game._tower_inactive(tower) and game.turret_states.get(socket_id) == state:
            return  # Retries and double clicks do not repeatedly heal.
        atom = atom_id if atom_id is not None else next((tag for tag, sid in game.atom_presence.items() if sid == socket_id), None)
        if tower is None:
            if atom is None:
                raise ValueError('Select or detect an Atom on this target before activating a new turret')
            validate_weapon(game, atom)
            kind = game.piece_roles[atom]
            previous = next((sid for sid in reversed(game.activation_order)
                             if sid in game.placements and not game._tower_inactive(game.placements[sid])), None)
            tower = game._new_tower(atom, socket_id, kind, state, 'operator')
            game.placements[socket_id] = tower
            game.activation_order.append(socket_id)
            if previous is not None:
                game._attempt_placement_link(previous, socket_id, source='operator')
            game._event('tower_placed', socket_id=socket_id, atom_tag_id=atom,
                        tower_type=kind, source='operator')
        elif tower.get('destroyed'):
            # Operator reactivation keeps the installed weapon and original owner.
            game._replace_tower(tower, tower['atom_tag_id'], tower['tower_type'], tower['owner'], 'operator')
        else:
            game._replenish_tower(tower, atom if atom is not None else tower['atom_tag_id'])
        activated(game, socket_id, state)
    # Consume an Atom already resting here. A real departure/return can activate
    # again, while unchanged camera frames cannot undo the operator command.
    for tag, sid in game.atom_presence.items():
        if sid == socket_id:
            game.atom_visits[tag] = {
                'socket_id': sid, 'departed': False,
                'accepted_at': max(game._physical_sampled_at, time.time()),
            }
    game._reconcile_connections(reason='operator_turret')
    game._evaluate_ring_topology()
    game._refresh_row_barriers()
    game._event('operator_turret', socket_id=socket_id, activation=state)


def core_blocked_reason(game):
    if game.phase != 'running':
        return 'Start the run before activating ArUco 38' if game.phase == 'setup' else 'Core controls are unavailable after the game ends'
    if game.core_stage in ('detonating', 'complete'):
        return 'The ArUco 38 sequence is already complete'
    if game.ring_completed_at is None:
        return 'Complete a force-field ring with 8-16 turrets first'
    return ''


def select_core(game, atom_id):
    if atom_id is not None and (type(atom_id) is not int or atom_id not in game.atom_owners):
        raise ValueError('Select a configured Atom ID')
    if atom_id is None:
        if game.phase != 'running' or game.core_stage in ('detonating', 'complete'):
            raise ValueError(core_blocked_reason(game))
        if game.core_stage != 'first_tag':
            return
        previous = game.core_first_tag
        game.core_stage = 'ring_ready' if game.ring_completed_at is not None else 'locked'
        game.core_first_tag = game.core_first_team = game.core_first_source = None
        game.core_first_tag_wall_at = None
        game.core_second_tag = game.core_second_source = None
        game.core_reset_wall_at = max(game._physical_sampled_at, game._placement_sampled_at, time.time())
        game._event('operator_core_cleared', atom_tag_id=previous)
        return
    if atom_id in (game.core_first_tag,game.core_second_tag):return
    reason = core_blocked_reason(game)
    if reason:
        raise ValueError(reason)
    if not game.virtual_play and atom_id in game.physical_atom_presence:
        raise ValueError('Physical Atom detection takes priority; move the physical Atom first')
    game.activate_core_tag(atom_id, source='operator')
    game._event('operator_core_selected', atom_tag_id=atom_id, stage=game.core_stage)


def snapshot(game):
    atoms = {sid: tag for tag, sid in game.atom_presence.items()}
    sockets = []
    for sid, socket in game.level.sockets.items():
        tower = game.placements.get(sid)
        last = game.turret_states.get(sid, 'initial')
        atom = atoms.get(sid)
        physical = atom is not None and not game.virtual_play and game.physical_atom_presence.get(atom) == sid
        sockets.append({
            'socket_id': sid, 'aruco_id': socket['aruco_id'],
            'activation': 'deactivated' if tower and game._tower_inactive(tower) else last,
            'last_activation_team': last if last in ('green', 'purple') else None,
            'atom_id': atom, 'atom_source': ('physical' if physical else 'manual') if atom is not None else None,
            'occupancy_status': 'ready' if atom is not None or not game.occupancy_error else 'unavailable',
        })
    return {'contract': 'photon.game.turret-controls', 'version': 1, 'sockets': sockets,
            'core': {'aruco_id': 38, 'blocked_reason': core_blocked_reason(game),
                     'can_clear': game.phase == 'running' and game.core_stage == 'first_tag',
                     'cleared': game.core_reset_wall_at is not None and game.core_stage == 'ring_ready'}}
