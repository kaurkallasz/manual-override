"""Write a repeatable browser-only stress scene; no running game or hardware.

Usage: .venv/bin/python tests/photon_performance_fixture.py /tmp/photon-scene.json
"""
import json
from pathlib import Path
import sys

from test_photon_framework import load


def build_fixture(count=1000, upgrade_level=1):
    level, game = load("photon-level"), load("photon-game")
    bundle = level.runtime_bundle()
    engine = game.DefenseEngine(bundle["runtime"], bundle["waves"])
    engine.set_virtual_play(True)
    if upgrade_level > 1:
        engine.set_virtual_test_loadout(dict.fromkeys(
            ('damage-machine-gun', 'damage-flamethrower', 'damage-mortar', 'damage-tesla-coil', 'forcefield'), upgrade_level))
    for index, socket in enumerate(engine.level.sockets):
        engine.place(100 + index % 4, socket, source="virtual")
    engine.runtime_time = engine.sim_time = 100
    state = engine.snapshot(compact_enemies=True)
    state.update(
        contract="photon.game", version=2, status="ready", phase="running", paused=False,
        level=game._simple_level(bundle["runtime"]), presentation=bundle["presentation"],
        configuration=game._configuration_snapshot(engine),
        inputs={"level": {"status": "ready"}, "board": {"status": "simulated"}},
        active_enemies=count, wave=4,
    )
    state["enemies"] = [dict(
        id=i + 1, enemy_type="brute" if i % 41 == 40 else "grunt",
        x=80 + (i % 40) * 38, y=90 + (i // 40) * 31, vx=10, vy=0,
        facing_x=1, facing_y=0, burn_until=110 if i % 4 == 0 else 0,
        electrocuted_until=110 if i % 4 == 1 else 0, electrocution_intensity=.8,
    ) for i in range(count)]
    for i, tower in enumerate([*state['towers'], *state.get('companions', [])]):
        tower.update(
            hp=tower["max_hp"] * .45, last_fire_at=100, weapon_charge=.8,
            last_fire_target={"x": 700, "y": 400, "enemy_id": i + 1},
            last_fire_chain=[dict(x=700 + j * 8, y=400 + j * 4, enemy_id=j + 1,
                                  intensity=1 - j / 20) for j in range(12)],
        )
    return state


if __name__ == "__main__":
    target = Path(sys.argv[1])
    target.write_text(json.dumps(build_fixture(int(sys.argv[2]) if len(sys.argv) > 2 else 1000)))
    print(target)
