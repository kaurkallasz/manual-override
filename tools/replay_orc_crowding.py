"""Offline crowd diagnostic from an exported attempt and Game event log.

This is a reconstruction, not an exact historical replay: frame timing, camera
occupancy and intermediate positions were not recorded. Never starts the Hub.
"""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from test_photon_framework import load


def describe(engine):
    enemies = list(engine.enemies.values())
    nearest = sorted(min((math.hypot(a['x'] - b['x'], a['y'] - b['y'])
                          for b in enemies if b['id'] != a['id']), default=0)
                     for a in enemies)
    archers = [a for a in enemies if engine.ranged.enabled(a)]
    return dict(seconds=round(engine.sim_time, 2), phase=engine.phase,
                alive=dict(Counter(a['enemy_type'] for a in enemies)),
                archer_states=dict(Counter(a.get('combat_state') for a in archers)),
                archer_targets=dict(Counter((a.get('ranged_target') or {}).get('key') for a in archers)),
                slow_melee=sum(not engine.ranged.enabled(a) and math.hypot(a['vx'], a['vy']) < 1 for a in enemies),
                road_blocked_melee=sum(not engine.ranged.enabled(a) and not a['attacking']
                                       and a['blocked_steps'] >= 100 for a in enemies),
                nearest_neighbor_median=nearest[len(nearest)//2] if nearest else None,
                neighbors_under_10px=sum(d < 10 for d in nearest), core_hp=engine.core_hp)


def replay(attempt, events, keep_atom, step=.1):
    game, level = load('photon-game'), load('photon-level')
    bundle = level.runtime_bundle()
    engine = game.DefenseEngine(bundle['runtime'], bundle['waves'])
    engine.set_virtual_play(True)
    engine.start(attempt['metadata']['settings'])
    pending = sorted((row['detail'] for row in events
                      if row.get('run_id') == attempt['run_id'] and row['kind'] == 'game_event'),
                     key=lambda row: row['at'])
    samples, next_sample = [], 500
    while engine.phase == 'running' and engine.sim_time < attempt['result']['active_seconds']:
        while pending and pending[0]['at'] <= engine.sim_time:
            event = pending.pop(0)
            if event['kind'] == 'virtual_test_loadout':
                engine.set_virtual_test_loadout(event['levels'], event['control'])
            elif event['kind'] in ('tower_placed', 'tower_replenished'):
                engine.place(event['atom_tag_id'], event['socket_id'], source='virtual')
                if not keep_atom:
                    engine.remove_atom(event['atom_tag_id'], source='virtual')
            elif event['kind'] == 'tower_aimed':
                engine.set_tower_aim(event['atom_tag_id'], event['angle'], event['reach'], socket_id=event['socket_id'])
        engine.step(step)
        if engine.sim_time >= next_sample:
            samples.append(describe(engine)); next_sample += 50
    samples.append(describe(engine))
    return dict(assumption='Atom stays until next recorded placement' if keep_atom else 'Atom lifted after every placement',
                map_revision=bundle['revision'], recorded_map_revision=attempt['metadata']['level_revision'],
                fixed_step_s=step, samples=samples, telemetry=engine.telemetry,
                final_snapshot=engine.snapshot())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('attempt', type=Path)
    parser.add_argument('events', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    attempt = json.loads(args.attempt.read_text())
    events = [json.loads(line) for line in args.events.read_text().splitlines() if line.strip()]
    result = dict(run_id=attempt['run_id'], evidence='conditional reconstruction; no historical positions recorded',
                  recorded_result=attempt['result'], replays=[])
    for keep_atom in (False, True):
        run = replay(attempt, events, keep_atom)
        result['replays'].append(run)
        print(json.dumps({k: v for k, v in run.items() if k not in ('telemetry', 'final_snapshot')}), flush=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
