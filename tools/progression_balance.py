"""Reproducible provisional balance audit. Temporary stores; no hub or hardware.

Run with the project Python. Placement times are design assumptions, never
inferred control-method labels from the historical pickup CSV.
"""
import argparse
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'hub'),str(ROOT)]
from test_photon_framework import load


def history_audit():
    path=ROOT/'sandboxes/gamemaster/prototypes/pickup-game/pickup-log.csv'
    with path.open(newline='') as handle:
        rows=[{'source_line':i,**row} for i,row in enumerate(csv.DictReader(handle),2)]
    times=[float(r['elapsed_seconds']) for r in rows]
    august=[r for r in rows if '2026-08-20'<=r['started_at']<'2026-08-24']
    return {'source':str(path.relative_to(ROOT)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'count':len(rows),'display_names':len({r['player'] for r in rows}),
            'range_seconds':[min(times),max(times)],'dates':sorted({r['started_at'][:10] for r in rows}),
            'august_20_four_day_rows':len(august),'method_speed_factors':None,
            'limitation':'No tier/settings/loadout metadata; no pooled median or inferred control-method gains.',
            'raw_records':rows}


def run_case(game,bundle,settings,tier,upgrade,slow_partner=False):
    engine=game.DefenseEngine(bundle['runtime'],bundle['waves'])
    engine.set_virtual_play(True)
    engine.set_virtual_test_loadout({key:upgrade for key in ('damage-machine-gun','damage-flamethrower','damage-mortar','damage-tesla-coil','forcefield')},tier)
    engine.start(settings)
    core=engine.level.core
    sockets=sorted(engine.level.sockets.items(),key=lambda pair:(pair[1]['x']-core['x'])**2+(pair[1]['y']-core['y'])**2)[:4]
    slots={code:socket_id for code,(socket_id,_) in zip((100,101,102,103),sockets)}
    trace=[(180,100),(240,102),(420,101),(480,103)]
    if slow_partner:trace=[(t+120 if code>=102 else t,code) for t,code in trace]
    trace.sort();pending=list(trace);next_replenish=600;peak=peak_backlog=0;actions=[]
    while engine.phase=='running' and engine.sim_time<1800:
        while pending and engine.sim_time>=pending[0][0]:
            at,code=pending.pop(0);engine.place(code,slots[code],source='virtual')
            actions.append({'at':at,'piece':code,'socket':slots[code],'kind':'placement'})
        if engine.sim_time>=next_replenish:
            for code in slots:
                engine.place(code,slots[code],source='virtual')
                actions.append({'at':next_replenish,'piece':code,'socket':slots[code],'kind':'replenish/replace'})
            next_replenish+=120
        engine.step(.1)
        peak=max(peak,len(engine.enemies));peak_backlog=max(peak_backlog,engine.pressure_bank)
    result=engine.snapshot(compact_enemies=True)
    return {'tier':tier,'upgrade_level':upgrade,'slow_partner':slow_partner,'seed':42055,
            'phase':result['phase'],'active_seconds':result['sim_time'],'kills':result['kills'],
            'core_hp':result['core_hp'],'peak_active_enemies':peak,'peak_deferred':peak_backlog,
            'released_orcs':result['released_orcs'],'schedule':game.orc_schedule(settings,bundle['waves'],tier),
            'actions':actions,'telemetry':engine.telemetry}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',default='docs/CONTROL_BALANCE_REPORT.json')
    parser.add_argument('--schedule-only',action='store_true');parser.add_argument('--tier',type=int)
    args=parser.parse_args()
    level,game=load('photon-level'),load('photon-game');bundle=level.runtime_bundle()
    from photon_game_runtime.settings import DEFAULTS
    spec=importlib.util.spec_from_file_location('balance_presets',ROOT/'sandboxes/gamemaster/prototypes/photon-game/presets.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    report={'status':'provisional','human_pilot':'not performed','historical_evidence':history_audit(),
            'assumptions':{'first_placements_s':[[180,100],[240,102],[420,101],[480,103]],
                           'replenishment_start_s':600,'replenishment_interval_s':120,'slow_partner_delay_s':120,
                           'source':'design assumptions; four nearest-core sockets, one per owned Atom; no core-tag shortcut',
                           'human_control_speed':'unmeasured; same action trace for each tier'},
            'map_revision':bundle['revision'],'scenarios':[]}
    map_id=bundle['runtime']['map_properties'].get('level_id','photon-level')
    with tempfile.TemporaryDirectory(prefix='ltz-balance-') as folder:
        presets=module.Presets(Path(folder)/'presets.json')
        for tier in ([args.tier] if args.tier else range(1,5)):
            settings,preset=presets.for_run(map_id,tier,DEFAULTS)
            if args.schedule_only:
                report['scenarios'].append({'tier':tier,'settings':settings,'schedule':game.orc_schedule(settings,bundle['waves'],tier)})
            else:
                for upgrade in (1,4):
                    result=run_case(game,bundle,settings,tier,upgrade)
                    report['scenarios'].append(result)
                    print(json.dumps({k:result[k] for k in ('tier','upgrade_level','phase','active_seconds','core_hp','peak_active_enemies')}),flush=True)
        if not args.schedule_only and not args.tier:
            settings,_=presets.for_run(map_id,1,DEFAULTS)
            report['scenarios'].append(run_case(game,bundle,settings,1,1,slow_partner=True))
    output=ROOT/args.output;output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')


if __name__=='__main__':main()
