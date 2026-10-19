"""Deterministic event combat traces; synthetic players, no hardware or data writes.
Reads the selected venue preset; writes only the requested report.
"""
import argparse,json,math,sys,time,tempfile,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'tests'),str(ROOT)]
from test_photon_framework import load


def trace(game,bundle,settings,level,turret_tier,spacing):
    e=game.DefenseEngine(bundle['runtime'],bundle['waves']);e.set_virtual_play(True)
    tracks=('damage-machine-gun','damage-flamethrower','damage-mortar','damage-tesla-coil')
    progression={side:{'control_tier':level,'levels':{**dict.fromkeys(tracks,turret_tier),'forcefield':level}} for side in ('green','purple')}
    saved={'level':level,'atoms':{'green':{'tag':100},'purple':{'tag':102}}}
    e.start(settings,progression=progression,event_game=saved)
    markers=(41,43,42,45,54,46,52,53);steps=[(20+i*spacing,e.level.socket_by_marker[m],100 if i%2==0 else 102) for i,m in enumerate(markers)]
    aim=repair=0;ring_at=None;stack_at=None
    from photon_game_runtime.engine import TOWER_STATS
    while e.phase=='running' and e.sim_time<1200:
        while steps and e.sim_time>=steps[0][0]:
            _,sid,tag=steps.pop(0);e.place(tag,sid,source='virtual');e.remove_atom(tag,source='virtual')
        if e.ring_completed_at is not None and ring_at is None:ring_at=e.sim_time
        if ring_at is not None and stack_at is None:
            e.activate_core_tag(100,source='virtual');e.activate_core_tag(102,source='virtual');stack_at=e.sim_time
        if e.sim_time>=repair:
            for sid,t in list(e.placements.items()):
                if t.get('destroyed'):
                    tag=t['atom_tag_id'];e.place(tag,sid,source='virtual');e.remove_atom(tag,source='virtual')
            repair+=30
        if e.sim_time>=aim:
            for sid,t in list(e.placements.items()):
                if t.get('destroyed') or not e.enemies:continue
                target=min(e.enemies.values(),key=lambda a:(a['x']-t['x'])**2+(a['y']-t['y'])**2)
                dx,dy=target['x']-t['x'],target['y']-t['y'];stats=TOWER_STATS[t['tower_type']]
                spread=max(0,min(1,(math.hypot(dx,dy)-stats['min_range'])/(stats['max_range']-stats['min_range']))) if t['tower_type']=='mortar' else 0
                e.set_tower_aim(t['atom_tag_id'],math.degrees(math.atan2(dy,dx)),spread,socket_id=sid)
            aim+=2
        e.step(.1)
    return {'game_level':level,'turret_tier':turret_tier,'placement_spacing_s':spacing,'ring_s':round(ring_at,1) if ring_at else None,'stack_s':round(stack_at,1) if stack_at else None,'outcome':e.phase,'seconds':round(e.sim_time,1),'combat_kills':sum(e.rewards.combat.values()),'core_hp':round(e.core_hp,1),'earned':e.rewards.checkpoint(final=e.phase in ('won','overrun'))['total_earned']}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--levels',default='1,2,3,4');args=parser.parse_args()
    game=load('photon-game');bundle=load('photon-level').runtime_bundle();map_id=game._simple_level(bundle['runtime'])['name'];folder=tempfile.TemporaryDirectory();preset_path=Path(folder.name)/'presets.json';shutil.copyfile(Path(game.DATA_DIR)/'level-presets.json',preset_path);store=game.Presets(preset_path);store.ensure_map(map_id,game._settings.snapshot())
    result={'source':'Synthetic reference traces using selected venue presets. No human speed or preference measurements.','map':map_id,'assumptions':['Eight alternating Machine Gun/Mortar turrets, one Atom per side; this remains a valid L4 subset.','Nearest-enemy aim every 2s and destroyed-turret repair every 30s. No occupancy boost.','Stop at stack victory, core loss, or 1200s. Same actions for each turret tier.'],'results':[]}
    for level in map(int,args.levels.split(',')):
        settings,preset=store.for_run(map_id,level,game._settings.snapshot())
        for turret,spacing in ((1,5),(2,5),(4,5),(1,20)):
            row=trace(game,bundle,settings,level,turret,spacing);row['preset_revision']=preset['revision'] if preset else None;result['results'].append(row)
            args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(row),flush=True)
