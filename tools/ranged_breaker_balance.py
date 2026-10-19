"""Seeded comparison using isolated stores and assumed placement traces.
No hardware, player writes or claims about human skill/credit balance.
"""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from test_photon_framework import load


def run(game,bundle,settings,tier,upgrade,scenario):
    e=game.DefenseEngine(bundle['runtime'],bundle['waves']);e.set_virtual_play(True)
    e.set_virtual_test_loadout(dict.fromkeys(('damage-machine-gun','damage-flamethrower','damage-mortar','damage-tesla-coil','forcefield'),upgrade),tier)
    core=e.level.core
    sockets=sorted(e.level.sockets,key=lambda sid:(e.level.sockets[sid]['x']-core['x'])**2+(e.level.sockets[sid]['y']-core['y'])**2)
    if scenario=='partial':trace=[(180,0),(240,1),(420,2),(480,3)]
    else:trace=[(180+i*15,i) for i in range(16)]
    e.start(settings);pending=list(trace);peak=0;stopped=0;destroyed=0;next_restore=600;stacked=False
    while e.phase=='running' and e.sim_time<1800:
        while pending and e.sim_time>=pending[0][0]:
            _,i=pending.pop(0);e.place(100+i%4,sockets[i],source='virtual')
        if e.sim_time>=next_restore:
            for i,sid in enumerate(sockets[:4] if scenario=='partial' else sockets):
                e.place(100+i%4,sid,source='virtual')
            next_restore+=120
        if scenario=='early-stack' and not stacked and e.sim_time>=650 and e.core_stage=='ring_ready':
            e.activate_core_tag(100,source='virtual');e.activate_core_tag(102,source='virtual');stacked=True
        before=sum(bool(t.get('destroyed')) for t in e.placements.values())
        e.step(.1)
        destroyed+=max(0,sum(bool(t.get('destroyed')) for t in e.placements.values())-before)
        peak=max(peak,len(e.enemies));stopped=max(stopped,sum(e.ranged.holding(a) for a in e.enemies.values()))
    return dict(scenario=scenario,tier=tier,upgrade=upgrade,mode=settings['breaker_attack_mode'],seed=42055,
        phase=e.phase,seconds=round(e.sim_time,1),core_hp=round(e.core_hp,2),kills=e.kills,released=e.next_enemy_id-1,
        peak_alive=peak,peak_stopped=stopped,towers_destroyed=destroyed,stacked=stacked,
        defense_bodies=len(e.placements)+sum(bool(t.get('companion')) for t in e.placements.values()),telemetry=e.telemetry)


if __name__=='__main__':
    game,level=load('photon-game'),load('photon-level');bundle=level.runtime_bundle()
    from photon_game_runtime.settings import DEFAULTS
    spec=importlib.util.spec_from_file_location('archer_presets',ROOT/'sandboxes/gamemaster/prototypes/photon-game/presets.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    results=[]
    with tempfile.TemporaryDirectory() as folder:
        store=module.Presets(Path(folder)/'presets.json')
        for scenario,tier,upgrade in [('partial',1,1),('full-rows',4,4),('early-stack',4,4)]:
            settings,_=store.for_run('fixture',tier,DEFAULTS)
            for mode in ('melee','ranged'):
                result=run(game,bundle,{**settings,'breaker_attack_mode':mode},tier,upgrade,scenario)
                results.append(result);print(json.dumps({k:v for k,v in result.items() if k!='telemetry'}),flush=True)
                Path(sys.argv[1] if len(sys.argv)>1 else '/tmp/archer-balance.json').write_text(json.dumps({
                    'status':'synthetic design traces; human playtest still required','placement_rule':'four nearby towers at 180/240/420/480s, or 16 towers every15s from180s; refill120s from600s; early stack>=650s when ring ready',
                    'map_revision':bundle['revision'],'scenarios':results},indent=2)+'\n')
