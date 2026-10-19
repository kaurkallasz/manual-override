"""Event Atom availability. A completed ring unlocks the center at any kill count."""

def allowed(game,tag):
    saved=getattr(game,'event_game',None)
    if not saved:return True  # Standalone engine fixtures have no event persistence.
    side=game.atom_owners.get(tag)
    return side in saved['atoms'] and (saved['level']==4 or tag==saved['atoms'][side]['tag'])

def require_atom(game,tag):
    if not allowed(game,tag):raise ValueError('This Atom is locked until game level L4')
