"""Seeded actual combat reference traces. Isolated, no hardware or player writes.
Deploy 16 primaries from 180–405s, reset destroyed pods from600s every120s.
At480s double-stack when allowed, or at650s manually aim each surviving pod at
its nearest living enemy every2s. These are design assumptions, not human logs.
"""
import argparse
import json
import math
from pathlib import Path
import sys
import tempfile
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tests'),str(ROOT)]
from test_photon_framework import load


def run(game,bundle,settings,tier,stack=False):
    e=game.DefenseEngine(bundle['runtime'],bundle['waves']);e.set_virtual_play(True)
    e.set_virtual_test_loadout(dict.fromkeys(('damage-machine-gun','damage-flamethrower','damage-mortar','damage-tesla-coil','forcefield'),tier),tier)
    sockets=sorted(e.level.sockets,key=lambda sid:(e.level.sockets[sid]['x']-e.level.core['x'])**2+(e.level.sockets[sid]['y']-e.level.core['y'])**2)
    e.start(settings);trace=[(180+i*15,i) for i in range(16)];refill=600;aim=650;stacked=False;peak_bodies=0;ticks=[];frames=[];progress=250
    while e.phase=='running' and e.sim_time<1800:
        while trace and e.sim_time>=trace[0][0]:
            _,i=trace.pop(0);e.place(100+i%4,sockets[i],source='virtual')
        if e.sim_time>=refill:
            for i,sid in enumerate(sockets):
                if e.placements.get(sid,{}).get('destroyed'):e.place(100+i%4,sid,source='virtual')
            refill+=120
        if e.sim_time>=480 and stack and not stacked and e.core_stage=='ring_ready':
            e.activate_core_tag(100,source='virtual');e.activate_core_tag(102,source='virtual');stacked=True
        if e.sim_time>=aim and not stack:
            for sid,tower in list(e.placements.items()):
                if tower.get('destroyed') or not e.enemies:continue
                target=min(e.enemies.values(),key=lambda a:(a['x']-tower['x'])**2+(a['y']-tower['y'])**2)
                dx,dy=target['x']-tower['x'],target['y']-tower['y']
                from photon_game_runtime.engine import TOWER_STATS
                stats=TOWER_STATS[tower['tower_type']]
                spread=max(0,min(1,(math.hypot(dx,dy)-stats['min_range'])/(stats['max_range']-stats['min_range']))) if tower['tower_type']=='mortar' else 1 if tower['tower_type']=='tesla_coil' else 0
                e.set_tower_aim(tower['atom_tag_id'],math.degrees(math.atan2(dy,dx)),spread,socket_id=sid)
            aim+=2
        started=time.perf_counter();e.step(.05 if len(e.enemies)>=900 else .1);elapsed=(time.perf_counter()-started)*1000
        if len(e.enemies)>=900:ticks.append(elapsed)
        bodies=len([t for t in e.placements.values() if not t.get('destroyed')])+sum(bool(t.get('companion')) and not t.get('destroyed') for t in e.placements.values());peak_bodies=max(peak_bodies,bodies)
        if len(e.enemies)==1000 and not frames:
            state=e.snapshot(compact_enemies=True);state.update(contract='photon.game',version=2,status='ready',level=game._simple_level(bundle['runtime']),presentation=bundle['presentation'],configuration=game._configuration_snapshot(e),inputs={'level':{'status':'ready'},'board':{'status':'simulated'}});frames.append(state)
        if e.sim_time>=progress:print(json.dumps({'tier':tier,'stack':stack,'seconds':round(e.sim_time),'alive':len(e.enemies),'kills':e.kills,'core':round(e.core_hp)}),flush=True);progress+=250
    from photon_game_runtime.engine import orc_schedule
    schedule=orc_schedule(settings,e.wave_source,tier);counts=e.ranged.counts
    result={'tier':tier,'stack':stack,'outcome':e.phase,'seconds':round(e.sim_time,2),'core_hp':e.core_hp,
            'scheduled':schedule['total'],'released':e.next_enemy_id-1,'remaining':len(e.enemies),'pressure_bank':e.pressure_bank,
            'counts':counts,'reward':e.rewards.checkpoint(final=e.phase in ('won','overrun')),'horde':e.rewards.horde,'peak_defense_bodies':peak_bodies,
            'dense_ticks':len(ticks),'dense_tick_p95_ms':sorted(ticks)[int(len(ticks)*.95)] if ticks else None,
            'settings':settings,'telemetry':e.telemetry}
    return result,frames[0] if frames else None

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--tiers',default='1,2,3,4');parser.add_argument('--stack',action='store_true');parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    game=load('photon-game');bundle=load('photon-level').runtime_bundle()
    from photon_game_runtime.settings import DEFAULTS
    import presets,horde_presets
    results=[]
    with tempfile.TemporaryDirectory() as folder:
        store=presets.Presets(Path(folder)/'presets.json')
        for tier in map(int,args.tiers.split(',')):
            base,_=store.for_run('fixture',tier,DEFAULTS);settings=horde_presets.candidate(base,tier)
            result,frame=run(game,bundle,settings,tier,args.stack);results.append(result)
            args.output.write_text(json.dumps({'seed':42055,'source':'synthetic placement and aiming assumptions; not human playtest','map_revision':bundle['revision'],'results':results},indent=2)+'\n')
            if frame:args.output.with_suffix('.frame.json').write_text(json.dumps(frame))
            print(json.dumps({k:v for k,v in result.items() if k not in ('telemetry','horde','settings','counts','reward')}),flush=True)
