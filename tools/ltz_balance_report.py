"""Offline balance evidence from explicit Progress JSON backups (never live SQLite).
Usage: python tools/ltz_balance_report.py exported-progress.json --output report.json
Missing historical class/health/preset evidence stays null. No automatic tuning.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import statistics


def summary(values):
    values=sorted(v for v in values if isinstance(v,(float,int)) and not isinstance(v,bool))
    if not values:return {'count':0,'p10':None,'median':None,'p90':None}
    return {'count':len(values),'p10':values[int((len(values)-1)*.1)],
            'median':statistics.median(values),'p90':values[int((len(values)-1)*.9)]}


def report(backup):
    tables=backup.get('tables',{})
    if not {'attempts','players','ledger'}<=tables.keys():raise ValueError('Progress backup with attempts, players and ledger required')
    attempts={};duplicates=0
    for row in tables['attempts']:
        a=json.loads(row['data']) if isinstance(row.get('data'),str) else row['data']
        key=a['run_id']
        if key in attempts:
            if a!=attempts[key]:raise ValueError('conflicting duplicate run '+key)
            duplicates+=1
        attempts[key]=a
    cohorts=defaultdict(list);practice=running=assisted=0
    for a in attempts.values():
        if not a['reward_enabled']:practice+=1;continue
        if a['outcome']=='running':running+=1;continue
        if a.get('assisted') or a.get('manual_advance') or a['outcome']=='operator_ended':assisted+=1;continue
        meta=a.get('metadata',{});preset=meta.get('level_preset') or {};reward=meta.get('reward_rules') or {}
        dimensions={'event_id':a.get('event_id'),'map':meta.get('level_id'),'layout_revision':meta.get('level_revision'),
                    'settings_hash':meta.get('settings_hash'),'preset_id':preset.get('id'),'preset_revision':preset.get('revision'),
                    'reward_revision':reward.get('revision'),'catalog_revision':a.get('catalog_revision'),
                    'loadouts':[{'side':p['side'],'tier':p['control_tier'],'levels':p['levels']} for p in a['participants']]}
        key=json.dumps(dimensions,sort_keys=True)
        cohorts[key].append(a)
    groups=[]
    for key,rows in cohorts.items():
        rewards=[r.get('reward') or {} for r in rows];results=[r.get('result') or {} for r in rows]
        telemetry=[r.get('telemetry') or {} for r in results]
        seconds=[r.get('active_seconds') if a['outcome']!='interrupted' else None for a,r in zip(rows,results)]
        earned=[a.get('kill_credits',a['kills'])+a.get('bonus_credits',0) for a in rows]
        health=[]
        for r in rewards:
            h=r.get('core_health_at_stack');health.append(h['hp']/h['max_hp'] if h and h.get('max_hp') else None)
        method={m:sum(r.get('victory_method')==m for r in rewards) for m in ('center_stack','waves_cleared')}
        method['unknown']=len(rows)-sum(method.values())
        comparison={}
        for m in ('center_stack','waves_cleared'):
            indexes=[i for i,r in enumerate(rewards) if r.get('victory_method')==m]
            comparison[m]={'n':len(indexes),'reward':summary([earned[i] for i in indexes]),
                           'credits_per_active_minute':summary([earned[i]*60/seconds[i] for i in indexes if seconds[i] and seconds[i]>0])}
        groups.append({'cohort':hashlib.sha256(key.encode()).hexdigest()[:16],'dimensions':json.loads(key),
                       'runs':len(rows),'run_ids':[a['run_id'] for a in rows],'wins':sum(a['outcome']=='won' for a in rows),
                       'victory_methods':method,'active_seconds':summary(seconds),'credits_per_player':summary(earned),
                       'wallet_at_start_per_player':summary([a.get('wallet_at_start',{}).get(p['player_id']) for a in rows for p in a['participants']]),
                       'wallet_after_save_per_player':summary([a.get('wallet_after_save',{}).get(p['player_id']) for a in rows for p in a['participants']]),
                       'fully_upgraded_at_start':sum(all(v==4 for v in p['levels'].values()) for a in rows for p in a['participants']),
                       'raw_kills':summary([a['kills'] for a in rows]),'bonus_credits':summary([r.get('stack_bonus') for r in rewards]),
                       'class_kills':{kind:summary([r.get('counts',{}).get(kind) for r in rewards]) for kind in ('grunt','runner','breaker','brute')},
                       'stack_health_fraction':summary(health),'peak_alive':summary([t.get('horde',{}).get('peak_alive') for t in telemetry]),
                       'longest_900_plus_s':summary([t.get('horde',{}).get('longest_900_plus_s') for t in telemetry]),
                       'stack_vs_survival':comparison,'recommendation':'Collect at least 10 wins per method in this cohort before changing bonus; compare reward per active minute and health together.'})
    players=[];ledger=defaultdict(list)
    for row in tables['ledger']:ledger[row['player_id']].append(row)
    for row in tables['players']:
        p=json.loads(row['data']) if isinstance(row['data'],str) else row['data']
        if p.get('is_test'):continue
        bought=[]
        for entry in ledger[p['id']]:
            detail=json.loads(entry['data']) if isinstance(entry['data'],str) else entry['data']
            if detail.get('kind')=='turret_upgrade':bought.append({'paid':-entry['amount'],**detail})
        players.append({'event_id':p.get('event_id'),'player_id':p['id'],'credits':p['credits'],'levels':p['levels'],'tier':p['current_control_tier'],
                        'wins_by_tier':p['wins_by_tier'],'lifetime_earned':p.get('lifetime_credits_earned',p['lifetime_score']),
                        'purchases':bought,'ledger_reconciles':sum(x['amount'] for x in ledger[p['id']])==p['credits']})
    return {'version':1,'source':'explicit Progress backup','unique_scored_runs':sum(len(v) for v in cohorts.values()),
            'duplicate_run_records_ignored':duplicates,'legacy_practice_excluded':practice,'assisted_excluded':assisted,'running_excluded':running,
            'cohorts':groups,'wallets':players,
            'balancing_protocol':['Separate cohorts by event, map, preset, settings, control level, turret tiers and reward revision.',
              'Exclude manually ended or advanced matches from automatic balance comparisons; retain their actual score in event history.',
              'Compare time-to-combat-target, core pressure, earnings and automatic purchases. Fast placement with basic turrets should lose pace at higher game levels.',
              'If early stacking dominates credits per minute, lower stack bonus fraction or forgone fraction; preserve the health incentive.',
              'If survival dominates both reward and player choice, inspect stack health, eligibility time and placement speed before changing rewards.',
              'Change one candidate parameter at a time; replay reference traces, then collect supervised human matches.',
              'Historical absent class, health, horde and bonus evidence is unknown; never infer it from raw kills.'],
            'limitations':['Synthetic traces do not measure human skill or preference.','No automatic activation or price changes.']}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('backup',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();source=args.backup.read_bytes();value=report(json.loads(source));value['source_sha256']=hashlib.sha256(source).hexdigest()
    args.output.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
    print(f"{value['unique_scored_runs']} scored matches, {len(value['cohorts'])} separate cohorts → {args.output}")
