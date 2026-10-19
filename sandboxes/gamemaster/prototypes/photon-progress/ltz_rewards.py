"""Validate Game's frozen cumulative reward evidence before committing currency."""
import math
TYPES=('grunt','runner','breaker','brute')

def integer(value,high=1000000000):
    if type(value) is not int or not 0<=value<=high:raise ValueError('invalid reward integer')
    return value

def migrate_player(p):
    p.setdefault('lifetime_kills',p['lifetime_score'])
    p.setdefault('lifetime_kill_credits',p['lifetime_score'])
    p.setdefault('lifetime_bonus_credits',0)
    p.setdefault('lifetime_credits_earned',p['lifetime_score'])
    return p

def banks_kill_credits(attempt):
    return attempt['reward_enabled']

def counts(value):
    if not isinstance(value,dict) or set(value)!=set(TYPES):raise ValueError('reward class counts required')
    return {k:integer(value[k]) for k in TYPES}

def rule(value):
    if not isinstance(value,dict) or type(value.get('version')) is not int or value['version']!=1:
        raise ValueError('reward rule v1 required')
    values=counts(value.get('values'))
    if any(not 1<=v<=1000 for v in values.values()) or values['brute']<=max(values[k] for k in TYPES if k!='brute'):
        raise ValueError('large brute must be worth more than smaller orcs')
    scheduled=counts(value.get('scheduled_counts'))
    if integer(value.get('scheduled_value'))!=sum(scheduled[k]*values[k] for k in TYPES):raise ValueError('scheduled reward mismatch')
    if not isinstance(value.get('revision'),str) or not 1<=len(value['revision'])<=80:raise ValueError('reward revision required')
    b=value.get('bonus',{})
    for k,lo,hi in [('stack_bonus_enabled',0,1),('stack_bonus_fraction',0,.5),('stack_health_exponent',1,3),('stack_forgone_fraction',0,.9)]:
        v=b.get(k)
        if type(v) not in (int,float) or not math.isfinite(v) or not lo<=v<=hi:raise ValueError('invalid bonus rule')
    if type(b['stack_bonus_enabled']) is not int:raise ValueError('invalid bonus enabled value')
    return value

def validate(a,data,final):
    frozen=a['metadata'].get('reward_rules')
    if frozen is None:
        if data.get('reward') is not None:raise ValueError('legacy attempt cannot accept new reward rules')
        return data['kills'],0,None
    r=rule(frozen);v=data.get('reward')
    if not isinstance(v,dict) or type(v.get('version')) is not int or v.get('version')!=1 or v.get('revision')!=r['revision']:raise ValueError('frozen reward evidence required')
    killed=counts(v.get('counts'));combat=counts(v.get('combat_kills'));purge=counts(v.get('purge_kills'))
    if sum(killed.values())!=data['kills'] or any(combat[k]+purge[k]!=killed[k] for k in TYPES):raise ValueError('reward kill counts do not reconcile')
    # Event matches always use their frozen schedule.
    if a['reward_enabled'] and any(killed[k]>r['scheduled_counts'][k] for k in TYPES):raise ValueError('reward kill counts do not reconcile')
    old=a.get('reward') or {}
    attribution=v.get('attribution')
    if attribution is not None:
        if not isinstance(attribution,dict) or type(attribution.get('version')) is not int or attribution['version']!=1 or attribution.get('method')!='lethal_damage':
            raise ValueError('invalid kill attribution')
        sides=attribution.get('kills')
        if not isinstance(sides,dict) or set(sides)!={'green','purple','shared','unattributed'}:
            raise ValueError('kill attribution counts required')
        if sum(integer(n) for n in sides.values())!=data['kills']:
            raise ValueError('kill attribution does not reconcile')
        previous=(old.get('attribution') or {}).get('kills',{})
        if any(sides[k]<previous.get(k,0) for k in sides):raise ValueError('kill attribution must be cumulative')
    elif old.get('attribution') is not None:
        raise ValueError('kill attribution cannot disappear')
    if any(killed[k]<old.get('counts',{}).get(k,0) for k in TYPES):raise ValueError('reward counts must be cumulative')
    credits=sum(killed[k]*r['values'][k] for k in TYPES)
    if integer(v.get('kill_credits'))!=credits:raise ValueError('weighted credits do not reconcile')
    if integer(v.get('sequence'))<old.get('sequence',0):raise ValueError('stale reward sequence')
    amount=0
    if final and data['outcome']=='won':
        method=v.get('victory_method')
        if method not in ('center_stack','waves_cleared'):raise ValueError('explicit victory method required')
        if method=='waves_cleared' and a['reward_enabled'] and killed!=r['scheduled_counts']:raise ValueError('all waves must be cleared')
        if method=='center_stack':
            # Older attempts may retain stack_combat_target metadata. It no
            # longer gates an accepted stack; keep counts and reward validation.
            health=v.get('core_health_at_stack') or {};hp=health.get('hp');maximum=health.get('max_hp')
            if any(type(x) not in (float,int) or not math.isfinite(x) for x in (hp,maximum)) or maximum<=0 or not 0<hp<=maximum:raise ValueError('accepted center health required')
            b=r['bonus'];potential=math.floor(r['scheduled_value']*b['stack_bonus_fraction']*(hp/maximum)**b['stack_health_exponent']+1e-9) if b['stack_bonus_enabled'] else 0
            cap=math.floor(max(0,r['scheduled_value']-credits)*b['stack_forgone_fraction']+1e-9);amount=min(potential,cap) if a['reward_enabled'] else 0
    if integer(v.get('stack_bonus'))!=amount or integer(v.get('total_earned'))!=credits+amount:raise ValueError('stack reward does not reconcile')
    return credits,amount,v
