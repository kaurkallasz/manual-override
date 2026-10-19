"""Read-only wave release windows from the simulation's actual clocks."""


def preview(timings):
    waves = [{'wave': t['wave'], 'start_s': round(t['start_s'], 3),
              'end_s': round(t['release_end_s'], 3), 'duration_s': round(t['duration_s'], 3),
              'state': 'upcoming'} for t in timings]
    return envelope(waves, 0., 0)


def envelope(waves, now, queued):
    return {'contract': 'photon.wave-timeline', 'version': 1, 'status': 'ready',
            'time_s': round(now, 3), 'end_s': max([w['end_s'] for w in waves]+[now, 1.]),
            'queued_orcs': queued, 'waves': waves}


def snapshot(engine, schedule):
    if engine.phase == 'setup':
        return preview(schedule['timings'])
    waves = []
    for wave in engine.launched_waves:
        complete = all(g['spawned'] >= g['count'] for g in wave['groups'])
        ends = []
        for group in wave['groups']:
            end = group.get('released_at')
            if end is None:
                end = (group['release_at']+group['release_duration_s'] if 'release_at' in group
                       else group.get('release_end_s', wave['started_at']))
                if group['spawned'] < group['count']:
                    end = max(end, engine.sim_time)
            ends.append(end)
        start, end = wave['started_at'], max(ends or [wave['started_at']])
        waves.append({'wave': wave['wave'], 'start_s': round(start, 3),
                      'end_s': round(end, 3), 'duration_s': round(end-start, 3),
                      'state': 'released' if complete else 'spawning'})
    for timing in schedule['timings'][engine.current_wave:]:
        start = engine.next_wave_at + (timing['wave']-engine.current_wave-1)*schedule['wave_interval_s']
        waves.append({'wave': timing['wave'], 'start_s': round(start, 3),
                      'end_s': round(start+timing['duration_s'], 3),
                      'duration_s': round(timing['duration_s'], 3), 'state': 'upcoming'})
    return envelope(waves, engine.sim_time, engine.pressure_bank)
