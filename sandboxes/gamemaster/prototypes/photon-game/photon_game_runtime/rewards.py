"""Authoritative match score, frozen reward rules and bounded horde evidence."""
import copy
import hashlib
import json
import math
from .kill_heatmap import KillHeatmap

TYPES=('grunt','runner','breaker','brute')
DEFAULTS={**{f'reward_{k}':v for k,v in zip(TYPES,(1,1,2,10))},
          'stack_bonus_enabled':1,'stack_bonus_fraction':.20,'stack_health_exponent':2.,'stack_forgone_fraction':.50}
RULES={**{f'reward_{k}':(int,1,1000) for k in TYPES},'stack_bonus_enabled':(int,0,1),
       'stack_bonus_fraction':(float,0,.5),'stack_health_exponent':(float,1,3),'stack_forgone_fraction':(float,0,.9)}

def schedule_counts(waves,schedule,settings):
    counts=dict.fromkeys(TYPES,0)
    for number,(wave,groups) in enumerate(zip(waves,schedule['groups']),1):
        offset=0
        for group,count in zip(wave['groups'],groups):
            brute=((offset+count)//41-offset//41) if number>=settings['brute_first_wave'] else 0
            counts['grunt' if group['enemy']=='brute' else group['enemy']]+=count-brute
            counts['brute']+=brute;offset+=count
    return counts

def rules(settings,waves,schedule):
    values={k:settings.get('reward_'+k,DEFAULTS['reward_'+k]) for k in TYPES}
    counts=schedule_counts(waves,schedule,settings)
    value={'version':1,'values':values,'scheduled_counts':counts,'scheduled_value':sum(counts[k]*values[k] for k in TYPES),
           'bonus':{k:settings.get(k,DEFAULTS[k]) for k in DEFAULTS if k.startswith('stack_')}}
    value['revision']=hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()[:20]
    return value

def bonus(rule,credits,health):
    remaining=max(0,rule['scheduled_value']-credits);b=rule['bonus']
    h=max(0.,min(1.,health))
    potential=math.floor(rule['scheduled_value']*b['stack_bonus_fraction']*h**b['stack_health_exponent']+1e-9) if b['stack_bonus_enabled'] else 0
    cap=math.floor(remaining*b['stack_forgone_fraction']+1e-9)
    return min(potential,cap),potential,cap

class MatchRewards:
    def __init__(self,engine):
        self.e=engine;self.eligible=True;self.rule=None;self.credits=0;self.sequence=0;self.victory_method=None
        self.counts=dict.fromkeys(TYPES,0);self.combat=dict.fromkeys(TYPES,0);self.purge=dict.fromkeys(TYPES,0)
        self.heatmap=KillHeatmap(engine.level)
        self.attribution=dict.fromkeys(('green','purple','shared','unattributed'),0)
        self.horde={'peak_alive':0,'peak_deferred':0,'seconds_at_cap':0.,'seconds_900_plus':0.,'longest_900_plus_s':0.,'timeline':[],'sample_interval_s':1.}
        self.streak=0.;self.next_sample=0.;self.stack_eligible_at=None

    def start(self,schedule):
        self.rule=rules(self.e.settings,self.e.wave_source,schedule)
        self.e.telemetry['reward_rules']=copy.deepcopy(self.rule)
        self.e.telemetry['horde']=self.horde

    def killed(self,enemy):
        self.heatmap.killed(enemy)
        kind=enemy['enemy_type'];self.counts[kind]+=1
        (self.purge if enemy.get('death_cause')=='core_purge' else self.combat)[kind]+=1
        self.credits+=(self.rule['values'] if self.rule else {k:DEFAULTS['reward_'+k] for k in TYPES})[kind]
        owner=enemy.get('kill_owner','unattributed')
        self.attribution[owner if owner in self.attribution else 'unattributed']+=1
        self.sequence+=1

    def sample(self,dt):
        e=self.e;h=self.horde;n=len(e.enemies)
        h['peak_alive']=max(h['peak_alive'],n);h['peak_deferred']=max(h['peak_deferred'],e.pressure_bank)
        if n>=e.settings['max_active_enemies']:h['seconds_at_cap']+=dt
        if n>=900:h['seconds_900_plus']+=dt;self.streak+=dt
        else:self.streak=0.
        h['longest_900_plus_s']=max(h['longest_900_plus_s'],self.streak)
        if e.ring_completed_at is not None and self.stack_eligible_at is None:
            self.stack_eligible_at=e.sim_time;e.telemetry['stack_eligible_at']=round(e.sim_time,3)
        if e.sim_time>=self.next_sample:
            h['timeline'].append([round(e.sim_time,2),e.current_wave,n,round(e.core_hp,2),e.kills,self.credits])
            if len(h['timeline'])>180:
                h['timeline']=h['timeline'][::2];h['sample_interval_s']*=2
            self.next_sample=e.sim_time+h['sample_interval_s']

    def checkpoint(self,final=False,outcome=None):
        rule=self.rule
        if not rule:return None
        e=self.e;health=e.telemetry.get('core_health_at_stack');method=self.victory_method
        amount=potential=cap=0
        if final and self.eligible and (outcome or e.phase)=='won' and method=='center_stack' and health:
            amount,potential,cap=bonus(rule,self.credits,health['hp']/health['max_hp'])
        return {'version':1,'revision':rule['revision'],'sequence':self.sequence,'kill_credits':self.credits,
                'counts':dict(self.counts),'combat_kills':dict(self.combat),'purge_kills':dict(self.purge),
                'attribution':{'version':1,'method':'lethal_damage','kills':dict(self.attribution)},
                'victory_method':method if final else None,'core_health_at_stack':copy.deepcopy(health),
                'core_health_at_finish':{'hp':e.core_hp,'max_hp':e.core_max_hp} if final else None,
                'stack_bonus':amount,'bonus_potential':potential,'bonus_cap':cap,'total_earned':self.credits+amount}

    def snapshot(self):
        value=self.checkpoint(final=self.e.phase in ('won','overrun'))
        if not value:return {'contract':'photon.match-score','version':1,'status':'unavailable'}
        live_value=sum(self.rule['values'][e['enemy_type']] for e in self.e.enemies.values() if e['hp']>0)
        estimate=bonus(self.rule,self.credits+live_value,self.e.core_hp/self.e.core_max_hp)[0]
        return {'contract':'photon.match-score','version':1,'status':'ready',**value,
                'values':dict(self.rule['values']),'scheduled_value':self.rule['scheduled_value'],
                'estimated_stack_total':self.credits+live_value+estimate,'estimated_stack_bonus':estimate,
                'peak_alive':self.horde['peak_alive'],'reward_enabled':self.eligible}
