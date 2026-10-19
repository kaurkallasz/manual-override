"""Game-owned weapon upgrade tuning, frozen with each run's settings."""

BONUS_KEYS = tuple(f'weapon_upgrade_l{level}_percent' for level in (2, 3, 4))
DEFAULTS = dict(zip(BONUS_KEYS, (30.0, 40.0, 50.0)), l4_turrets_per_socket=2)
RULES = {**{key: (float, 0.0, 500.0) for key in BONUS_KEYS},
         'l4_turrets_per_socket': (int, 1, 2)}


def multiplier(settings, level):
    if level <= 1:
        return 1.0
    key = BONUS_KEYS[level - 2]
    return 1.0 + float(settings.get(key, DEFAULTS[key])) / 100.0


def projection(settings, sockets):
    return {'contract': 'photon.game.weapon-upgrades', 'version': 1,
            'bonus_percent': {str(level): float(settings.get(key, DEFAULTS[key]))
                              for level, key in zip((2, 3, 4), BONUS_KEYS)},
            'l4_turrets_per_socket': settings.get('l4_turrets_per_socket', 2),
            'companion_eligible': sum(bool(s.get('companion', {}).get('eligible')) for s in sockets.values()),
            'primary_sockets': len(sockets)}
