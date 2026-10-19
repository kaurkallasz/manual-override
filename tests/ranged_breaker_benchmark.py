"""Reproducible isolated 1,000-enemy combat/renderer load; no hardware or saved state.
Run: PYTHONPATH=tests .venv/bin/python tests/ranged_breaker_benchmark.py /tmp/archer
Synthetic placements/hit points sustain stress. This is not a balance playtest.
"""
import copy
import json
import math
from pathlib import Path
import sys
import time
from test_photon_framework import load


def scene(mode='ranged', all_archers=False, count=1000):
    game, level = load('photon-game'), load('photon-level')
    bundle = level.runtime_bundle()
    e = game.DefenseEngine(bundle['runtime'], bundle['waves'])
    e.set_virtual_play(True)
    e.set_virtual_test_loadout(dict.fromkeys(('damage-machine-gun', 'damage-flamethrower',
        'damage-mortar', 'damage-tesla-coil', 'forcefield'), 4))
    for i, sid in enumerate(e.level.sockets):e.place(100+i%4, sid, source='virtual')
    e.start({'breaker_attack_mode':mode,'first_wave_delay_s':1500,'core_hp':100000})
    # A fixed spatial sample spans the map and all facing directions. Reuse real
    # spawned route/physics records, with large HP only to keep the stress dense.
    for i in range(count):
        kind = 'breaker' if all_archers or i%100<28 else ('grunt' if i%100<73 else 'runner' if i%100<98 else 'brute')
        assert e._spawn_enemy(kind,{})
        enemy=e.enemies[e.next_enemy_id-1]
        enemy.update(x=90+(i%40)*38,y=85+(i//40)*32,hp=100000,max_hp=100000,next_scan_at=(i%4)*.05)
    for tower in e.placements.values():tower.update(hp=100000,max_hp=100000)
    return e,game,bundle


def public(e,game,bundle):
    state=e.snapshot(compact_enemies=True)
    state.update(contract='photon.game',version=2,status='ready',
        level=game._simple_level(bundle['runtime']),presentation=bundle['presentation'],
        configuration=game._configuration_snapshot(e),inputs={'level':{'status':'ready'},'board':{'status':'simulated'}})
    return state


def percentile(values,p):return round(sorted(values)[min(len(values)-1,int(len(values)*p))],3)


def measure(mode,all_archers):
    e,game,bundle=scene(mode,all_archers)
    ticks=[];snapshots=[];sizes=[];peak=0;hold_peak=0;backlog=0;max_backlog=0
    fixture=None
    for i in range(160):
        start=time.perf_counter();e.step(.05);elapsed=(time.perf_counter()-start)*1000
        ticks.append(elapsed);backlog=max(0,backlog+elapsed-50);max_backlog=max(max_backlog,backlog)
        peak=max(peak,len(e.ranged.arrows));hold_peak=max(hold_peak,sum(e.ranged.holding(x) for x in e.enemies.values()))
        if i%2==0:
            start=time.perf_counter();state=public(e,game,bundle)
            sizes.append(len(json.dumps(state,separators=(',',':'))));snapshots.append((time.perf_counter()-start)*1000)
            if fixture is None or len(state['enemy_arrows'])>len(fixture['enemy_arrows']):fixture=copy.deepcopy(state)
    return dict(mode=mode,mix='all archers' if all_archers else '28% breakers',ticks=len(ticks),
        active=len(e.enemies),defense_bodies=len(fixture['towers'])+len(fixture['companions']),
        tick_ms={str(p):percentile(ticks,p) for p in (.5,.95,.99,1)},
        ticks_over_50_ms=sum(t>50 for t in ticks),backlog_peak_ms=round(max_backlog,2),
        snapshot_p95_ms=percentile(snapshots,.95),snapshot_max_bytes=max(sizes),
        peak_arrows=peak,peak_stopped=hold_peak,stats=dict(e.ranged.stats)),fixture


if __name__=='__main__':
    prefix=Path(sys.argv[1] if len(sys.argv)>1 else '/tmp/archer')
    results=[]
    for mode,all_archers in [('melee',False),('ranged',False),('ranged',True)]:
        result,fixture=measure(mode,all_archers);results.append(result);print(json.dumps(result),flush=True)
        if mode=='ranged':Path(str(prefix)+('-worst' if all_archers else '-mix')+'.json').write_text(json.dumps(fixture))
    Path(str(prefix)+'-engine.json').write_text(json.dumps(results,indent=2)+'\n')
