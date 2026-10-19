"""Retiming of unreleased practice enemies; no reset of combat or earned progress."""
from . import rewards

SPAWN_KEYS = ('wave_count', 'wave_interval_s', 'first_wave_delay_s',
              'release_rate_multiplier', 'enemy_count_multiplier', 'difficulty_offset',
              'brute_first_wave', 'max_active_enemies') + tuple(
    f'control_{kind}_multiplier_{tier}' for kind in ('orc', 'pace')
    for tier in ('joint', 'xyz', 'image', 'cue'))


def describe(schedule, preset=None):
    return {'tier': schedule['tier'], 'preset': (preset or {}).get('name', 'Settings draft'),
            'preset_revision': (preset or {}).get('revision'),
            'total': schedule['total'], 'saved_tier_total': schedule['total'],
            'wave_interval_s': schedule['wave_interval_s'],
            'release_rate_multiplier': schedule['release_rate_multiplier']}


def apply(engine, settings, tier, preset, schedule_fn):
    """Called under the engine lock after the complete unlock command is validated."""
    old = schedule_fn(engine.settings, engine.wave_source, engine.contract_control_tier)
    updated = {**engine.settings, **{k: settings[k] for k in SPAWN_KEYS}}
    schedule = schedule_fn(updated, engine.wave_source, tier)
    # Reapplying the same selection must not restart release clocks or dwell.
    if (engine.spawn_intensity is not None and engine.contract_control_tier == tier
            and all(engine.settings[k] == updated[k] for k in SPAWN_KEYS)):
        engine.spawn_intensity.update(preset=(preset or {}).get('name', 'Settings draft'),
                                      preset_revision=(preset or {}).get('revision'))
        return
    running = engine.phase == 'running'
    if running:
        old_wait = old['wave_interval_s'] if engine.current_wave else old['first_wave_delay_s']
        new_wait = schedule['wave_interval_s'] if engine.current_wave else schedule['first_wave_delay_s']
        fraction = min(1., max(0., (engine.next_wave_at-engine.sim_time)/old_wait)) if old_wait else 0.
        engine.next_wave_at = engine.sim_time + fraction*new_wait
        for wave in engine.launched_waves:
            planned = schedule['groups'][wave['wave']-1] if wave['wave'] <= len(schedule['groups']) else []
            for i, group in enumerate(wave['groups']):
                if group['spawned'] >= group['count']:
                    continue  # Completed groups never reopen when intensity increases.
                count = max(group['spawned'], planned[i] if i < len(planned) else 0)
                duration = max(.1, float(group.get('duration_s', 1))/max(.05, schedule['release_rate_multiplier']))
                group.update(count=count, release_at=engine.sim_time, release_start=group['spawned'],
                             release_duration_s=max(.1, duration*(count-group['spawned'])/max(1, count)))
                if count == group['spawned']:
                    group['released_at'] = engine.sim_time
    engine.settings.update({k: updated[k] for k in SPAWN_KEYS})
    engine.contract_control_tier = tier
    engine.spawn_intensity = describe(schedule, preset)
    if running:
        # Account for the mixed practice schedule: completed/queued enemies stay
        # in their original groups; future groups use the newly selected tier.
        counts = dict.fromkeys(rewards.TYPES, 0)
        launched = {w['wave']: w['groups'] for w in engine.launched_waves}
        for number in range(1, max(len(schedule['groups']), engine.current_wave)+1):
            if number in launched:
                groups = launched[number]
            else:
                offset = 0
                groups = []
                for source, count in zip(engine.wave_source[number-1]['groups'], schedule['groups'][number-1]):
                    groups.append({**source, 'count': count, 'spawn_offset': offset,
                                   'brute_interval': 41 if number >= updated['brute_first_wave'] else 0})
                    offset += count
            for group in groups:
                count, offset, interval = group['count'], group['spawn_offset'], group['brute_interval']
                brute = ((offset+count)//interval-offset//interval) if interval else 0
                counts['grunt' if group['enemy'] == 'brute' else group['enemy']] += count-brute
                counts['brute'] += brute
        engine.ranged.counts['scheduled'] = counts
        # Credit weights and receipt identity stay frozen, even for practice.
        # Only the spawning telemetry follows this changing practice schedule.
        engine.spawn_intensity['total'] = sum(counts.values())
        changes = engine.telemetry.setdefault('practice_intensity_changes', [])
        changes.append({**engine.spawn_intensity, 'at': engine.sim_time})
        del changes[:-16]
        engine._event('practice_intensity_changed', **engine.spawn_intensity)
