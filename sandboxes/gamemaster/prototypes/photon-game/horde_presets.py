"""Explicit opt-in horde candidates; never replace a saved selection."""
NAME='LTZ score and horde candidate'
FAMILY='ltz-horde-v1'
REVISION=1

def candidate(base,tier):
    value={**base,'breaker_attack_mode':'ranged','max_active_enemies':(150,350,650,1000)[tier-1],
           'reward_grunt':1,'reward_runner':1,'reward_breaker':2,'reward_brute':10,
           'stack_bonus_enabled':1,'stack_bonus_fraction':.2,'stack_health_exponent':2.,'stack_forgone_fraction':.5}
    value.update(enemy_count_multiplier=(.26,.25,.25,.72)[tier-1],wave_interval_s=(95.,24.,12.,8.)[tier-1],release_rate_multiplier=(1.4,2.,3.,4.)[tier-1],
                 enemy_health_multiplier=(1.6,1.3,1.5,1.)[tier-1])
    if tier in (2,3):value.update(enemy_core_damage_multiplier=.025,enemy_tower_damage_multiplier=.06,defense_unit_health_percent=30.)
    if tier==4:
        value.update(enemy_count_multiplier=.72,first_wave_delay_s=420.,wave_interval_s=8.,
                     release_rate_multiplier=4.,enemy_core_damage_multiplier=.025,
                     enemy_tower_damage_multiplier=.06,defense_unit_health_percent=30.)
    return value
