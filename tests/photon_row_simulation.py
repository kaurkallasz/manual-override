"""Isolated 1,000-enemy server stress replay with all 16 row states.

Usage: .venv/bin/python tests/photon_row_simulation.py /tmp/row-simulation.json
Uses fixture HP to retain the load; never starts a server or touches settings.
"""
import copy
import json
import math
from pathlib import Path
import statistics
import sys
import time
from test_photon_framework import load


def run(ticks=480, upgrade_level=1, enable_companions=True):
    bundle=load('photon-level').runtime_bundle()
    if not enable_companions:
        bundle=copy.deepcopy(bundle)
        for socket in bundle['runtime']['sockets'].values():socket.pop('companion',None)
    e=load('photon-game').DefenseEngine(bundle['runtime'],bundle['waves'])
    e.set_virtual_play(True)
    if upgrade_level > 1:
        e.set_virtual_test_loadout(dict.fromkeys(
            ('damage-machine-gun','damage-flamethrower','damage-mortar','damage-tesla-coil','forcefield'),upgrade_level))
    for i,socket in enumerate(e.level.sockets):e.place(100+i%4,socket,source='virtual')
    e.runtime_time=4;e._refresh_row_barriers();e.start()
    e.core_hp=e.core_max_hp=1e12
    for tower in e.placements.values():tower['hp']=tower['max_hp']=1e12
    templates=[]
    for lane in ('top_outer','bottom_outer'):
        e._spawn_enemy('grunt',{lane:1})
        templates.append(copy.deepcopy(e.enemies[e.next_enemy_id-1]))
    e.enemies.clear()
    for i in range(1000):
        enemy=copy.deepcopy(templates[i%2]);enemy.update(id=i+1,hp=1e9,max_hp=1e9)
        if i%41==40:enemy['enemy_type']='brute'
        path=enemy['path'];lengths=[math.dist(a,b) for a,b in zip(path,path[1:])]
        position=sum(lengths)*((i//2+.25)/500)
        for index,length in enumerate(lengths):
            if position <= length:
                fraction=position/max(length,1e-9);a,b=path[index],path[index+1]
                enemy.update(x=a[0]+(b[0]-a[0])*fraction,y=a[1]+(b[1]-a[1])*fraction,segment=index,
                             vx=0,vy=0)
                break
            position-=length
        e.enemies[i+1]=enemy
        e._sync_enemy_road_edge(enemy,search_all=True)
    e.next_enemy_id=1001
    timings=[];queues=[];builds=[]
    for tick in range(ticks):
        if tick%30==0:
            mask=tick//30
            for i,row in enumerate(e.level.row_barriers):
                e.placements[row['socket_ids'][0]]['destroyed']=not bool(mask & (1<<i))
        before=time.perf_counter();e.step(1/30);timings.append((time.perf_counter()-before)*1000)
        queues.append(len(e._row_reroute_queue));builds.append(e.row_route_builds)
        assert len(e.enemies)==1000
    ordered=sorted(timings)
    return dict(ticks=len(timings),enemies=len(e.enemies),row_masks=16,
                median_tick_ms=statistics.median(timings),p95_tick_ms=ordered[int(.95*len(ordered))],
                max_tick_ms=max(timings),ticks_over_33ms=sum(t>1000/30 for t in timings),
                routing_builds=builds[-1],max_pending_routes=max(queues),pending_at_end=queues[-1],
                queued_spawns=e.pressure_bank)


if __name__=='__main__':
    result=run(int(sys.argv[2]) if len(sys.argv)>2 else 480);Path(sys.argv[1]).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
