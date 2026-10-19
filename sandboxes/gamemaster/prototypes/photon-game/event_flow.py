"""Resolve a new game's starting Atoms from stable Board evidence or GM input."""
from photon_game_runtime import event_rules


def starting_atoms(engine,saved,observation,requested):
    if not isinstance(requested,dict) or not set(requested)<= {'green','purple'}:raise ValueError('Invalid starting Atom selection')
    if saved['atoms']:
        for side,atom in saved['atoms'].items():
            if engine.atom_owners.get(atom['tag'])!=side or 'damage-'+engine.piece_roles[atom['tag']].replace('_','-')!=atom['track']:
                raise ValueError('Configured ArUco roles differ from this save; restore its piece codes')
            if requested.get(side) not in (None,atom['tag']):raise ValueError('Starting Atoms are fixed in this save')
        atoms=saved['atoms']
    else:
        atoms={}
        occupancy=observation.get('occupancy',{})
        for side in ('green','purple'):
            manual=requested.get(side)
            if manual is not None:
                if type(manual) is not int or engine.atom_owners.get(manual)!=side:raise ValueError('Select a configured Atom for its own team')
                tag=manual;source='gamemaster'
            else:
                seen={r['movable_id'] for r in occupancy.get('relations',[]) if occupancy.get('status')=='ready' and r.get('state')=='present' and engine.atom_owners.get(r['movable_id'])==side}
                if not seen and observation.get('status')=='ready':
                    seen={r['movable_id'] for r in observation.get('relations',[]) if r.get('stable') and engine.atom_owners.get(r['movable_id'])==side}
                if len(seen)!=1:raise ValueError(f'Place one {side} Atom on a numbered target, or choose it in Game Master for camera fallback')
                tag=seen.pop();source='camera'
            atoms[side]={'tag':tag,'track':'damage-'+engine.piece_roles[tag].replace('_','-'),'source':source}
    for tower in engine.placements.values():
        if saved['level']<4 and tower['atom_tag_id']!=atoms[tower['owner']]['tag']:
            raise ValueError('Reset the playfield: a locked second Atom has already installed a turret')
    return atoms
