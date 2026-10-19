"""Game-owned next-match projection and authenticated economy facade."""
import copy
import json
from photon_game_runtime.engine import orc_schedule, DEFAULT_SETTINGS
from photon_game_runtime import rewards, upgrades

_cache={}
_result_cache={}

def economy(module_reader,value=None):
    owner=module_reader('photon-progress')
    function='economy_snapshot' if value is None else 'economy_command'
    if owner is None or not callable(getattr(owner,function,None)):raise ValueError('Upgrade catalog unavailable')
    result=getattr(owner,function)(*(() if value is None else (value,)))
    if not isinstance(result,dict) or result.get('contract')!='photon.progress.economy' or type(result.get('version')) is not int or result['version']!=1 or result.get('status')!='ready':raise ValueError('Upgrade catalog contract unavailable')
    return result

def preview(presets,engine,map_id,base):
    if presets is None or engine is None:return {'contract':'photon.next-match','version':1,'status':'unavailable'}
    store=presets.snapshot()
    key=json.dumps([map_id,engine.level.layout_revision,store['revision'],engine.wave_source,base],sort_keys=True)
    if _cache.get('key')==key:return copy.deepcopy(_cache['value'])
    tiers=[]
    for tier in range(1,5):
        selected=store['selected'].get(f'{map_id}:{tier}')
        p=next((p for p in store['presets'] if p['id']==selected),None)
        settings={**DEFAULT_SETTINGS,**(p['settings'] if p else base)}
        schedule=orc_schedule(settings,engine.wave_source,tier)
        rule=rewards.rules(settings,engine.wave_source,schedule)
        tiers.append({'tier':tier,'preset':p['name'] if p else 'Settings draft','preset_revision':p['revision'] if p else None,
                      'total':schedule['total'],'waves':schedule['waves'],'wave_interval_s':schedule['wave_interval_s'],
                      'release_rate_multiplier':schedule['release_rate_multiplier'],'scheduled_counts':rule['scheduled_counts'],
                      'timings':schedule['timings'],
                      'full_clear_credits':rule['scheduled_value'],'reward_revision':rule['revision'],'values':rule['values'],
                      'breaker_mode':settings['breaker_attack_mode'],'max_active_enemies':settings['max_active_enemies'],
                      'weapon_upgrades':upgrades.projection(settings, engine.level.sockets),
                      'companion_eligible':sum(bool(s.get('companion', {}).get('eligible')) for s in engine.level.sockets.values()) if settings['l4_turrets_per_socket'] == 2 else 0,
                      'primary_sockets':len(engine.level.sockets)})
    value={'contract':'photon.next-match','version':1,'status':'ready','map_id':map_id,'tiers':tiers,
           'survival_credits_before_cue':sum(t['full_clear_credits'] for t in tiers[:3])}
    _cache.update(key=key,value=value)
    return copy.deepcopy(value)

def save_state(progress,run_id,phase):
    saved=(progress.get('result') or {}).get('run_id')==run_id
    return {'run_id':run_id,'status':'saved' if saved else 'saving' if phase in ('won','overrun','operator_ended','aborted') else 'playing',
            'error':progress.get('error')}


def loadouts(module_reader,phase):
    owner=module_reader('photon-progress')
    try:
        if owner is None or not callable(getattr(owner,'progress_snapshot',None)):raise ValueError('Progress unavailable')
        result=owner.progress_snapshot()
        if result.get('contract')!='photon.progress' or type(result.get('version')) is not int or result['version']!=2 or result.get('status')!='ready':raise ValueError('Progress v2 unavailable')
        receipts={}
        if phase in ('won','overrun','operator_ended'):
            key=(id(owner),result['revision'])
            if _result_cache.get('key')!=key:
                for side in result['roster']:
                    value=owner.public_snapshot(side)
                    if value.get('contract')!='photon.progress' or type(value.get('version')) is not int or value['version']!=2 or value.get('status')!='ready':raise ValueError('Level result unavailable')
                    receipts[side]=value.get('latest_result')
                _result_cache.update(key=key,value=copy.deepcopy(receipts))
            else:receipts=copy.deepcopy(_result_cache['value'])
        return {'status':'ready','events':result['events'],'saved_games':result['saved_games'],'level_results':receipts,'teams':{side:{'name':p['name'],'id':p['id'],'revision':p['revision'],'tier':p['selected_control'],'levels':p['levels'],'progression_stage':p['progression_stage']} for side,p in result['roster'].items()}}
    except Exception as exc:return {'status':'unavailable','error':str(exc)}
