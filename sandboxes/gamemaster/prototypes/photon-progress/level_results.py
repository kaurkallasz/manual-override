"""Versioned event results for local celebrations and a future scoreboard consumer.

Only completed results are exposed. Team identity is the event and unordered pair,
so swapping phone colours or loading another save does not split team history.
"""
import copy
import json
import math
import statistics

from ltz_records import fingerprint, identifier, finite, integer

FINISHED = ('won', 'overrun', 'operator_ended')


def validate_heatmap(value, kills):
    if value is None:return  # Older results have no location evidence.
    if not isinstance(value,dict) or type(value.get('version')) is not int or value['version']!=1:
        raise ValueError('Invalid kill heatmap')
    cols=integer(value.get('columns'),1,64);rows=integer(value.get('rows'),1,64)
    width=finite(value.get('width'));height=finite(value.get('height'))
    if width<=0 or height<=0:raise ValueError('Invalid heatmap dimensions')
    counts=value.get('counts')
    if not isinstance(counts,list) or len(counts)!=cols*rows:raise ValueError('Invalid heatmap cells')
    total=sum(integer(n) for n in counts)+integer(value.get('unlocated'))
    if total!=kills:raise ValueError('Heatmap kills do not reconcile')
    roads=value.get('roads',[]);markers=value.get('markers',[])
    if not isinstance(roads,list) or len(roads)>256 or not isinstance(markers,list) or len(markers)>128:
        raise ValueError('Invalid heatmap landmarks')
    if any(not isinstance(road,list) or not 2<=len(road)<=256 for road in roads) or sum(map(len,roads))>2048:
        raise ValueError('Invalid heatmap roads')
    for point in [p for road in roads for p in road]:
        if not isinstance(point,list) or len(point)!=2:raise ValueError('Invalid heatmap point')
        for v in point:finite(v,-1000000)
    for marker in markers:
        if not isinstance(marker,list) or len(marker)!=3:raise ValueError('Invalid heatmap marker')
        finite(marker[0],-1000000);finite(marker[1],-1000000);integer(marker[2],0,999)
    core=value.get('core')
    if not isinstance(core,list) or len(core)!=2:raise ValueError('Invalid heatmap core')
    if not 0<=finite(core[0])<=width or not 0<=finite(core[1])<=height:
        raise ValueError('Invalid heatmap core')


def team_id(attempt):
    return fingerprint({'event': attempt['event_id'],
                        'players': sorted(p['player_id'] for p in attempt['participants'])})


def summary(a):
    result = a.get('result') or {}
    reward = a.get('reward') or {}
    attribution = reward.get('attribution')
    kills = dict(attribution['kills']) if attribution else {
        'green': None, 'purple': None, 'shared': None, 'unattributed': a['kills']}
    atoms=[]
    for p in a['participants']:
        if a.get('unlocks',{}).get(p['player_id'])==4:
            tracks=('damage-machine-gun','damage-flamethrower') if p['side']=='green' else ('damage-mortar','damage-tesla-coil')
            atoms.extend({'player_id':p['player_id'],'track':t,'level':p['levels'][t]} for t in tracks if t not in p.get('eligible_tracks',[]))
    return {'run_id': a['run_id'], 'event_id': a['event_id'], 'team_id': team_id(a),
            'finished_at': a['finished_at'], 'level': a['metadata'].get('contract_control_tier', 1),
            'outcome': a['outcome'], 'assisted': bool(a.get('assisted') or a.get('manual_advance')),
            'score': a.get('kill_credits', a['kills']), 'total_kills': a['kills'],
            'kill_attribution': kills, 'attribution_method': 'lethal_damage' if attribution else 'unavailable',
            'active_seconds': result.get('active_seconds'),
            'players': [{k: p[k] for k in ('player_id', 'name', 'side')} for p in a['participants']],
            'turrets_unlocked': {pid:[{k:b[k] for k in ('track','level','price','forced')} for b in bought]
                                for pid,bought in a.get('purchases',{}).items()},
            'atoms_unlocked': atoms,
            'controls_unlocked': copy.deepcopy(a.get('unlocks', {}))}


def comparison(score, baseline, count):
    return {'baseline': baseline, 'sample_count': count, 'delta': score - baseline,
            'percent': (score - baseline) / baseline * 100 if baseline else None}


def cohort(a):
    # Upgrades are deliberately excluded: earned equipment is part of performance.
    m = a['metadata']
    return fingerprint({k: m.get(k) for k in ('level_id','level_revision','contract_control_tier',
                        'settings','reward_rules','orc_schedule','scoring_version',
                        'enemy_combat_version','companion_policy','core_rule_version')})


def attempts(db, event_id):
    return [json.loads(r[0]) for r in db.execute(
        "SELECT data FROM attempts WHERE json_extract(data,'$.event_id')=? "
        "AND json_extract(data,'$.outcome') IN ('won','overrun','operator_ended') "
        "ORDER BY json_extract(data,'$.finished_at'),id", (event_id,))]


def statistics_at_finish(a, previous):
    current = summary(a)
    previous = [r for r in previous if (r['finished_at'],r['run_id']) < (a['finished_at'],a['run_id'])]
    own = [r for r in previous if r['run_id'] != a['run_id'] and team_id(r) == current['team_id']]
    score = current['score']
    prior_scores = [r.get('kill_credits', r['kills']) for r in own]
    other = {}
    if not current['assisted']:
        for r in previous:
            if (team_id(r) != current['team_id'] and cohort(r) == cohort(a)
                    and not r.get('assisted') and not r.get('manual_advance')):
                other.setdefault(team_id(r), []).append(r.get('kill_credits', r['kills']))
    means = [statistics.mean(values) for values in other.values()]
    return {'version': 1, 'metric': 'weighted_kill_score', 'team_id': current['team_id'],
            'comparison_scope': 'previous completed team matches; event peers use identical level and rules',
            'previous': comparison(score, prior_scores[-1], 1) if prior_scores else None,
            'average': comparison(score, statistics.mean(prior_scores), len(prior_scores)) if prior_scores else None,
            'other_teams': {**comparison(score, statistics.mean(means), len(means)),
                            'rank': 1 + sum(value > score for value in means),
                            'team_count': len(means) + 1} if means else None,
            'event_comparison_status': 'assisted' if current['assisted'] else 'ready' if means else 'no_peers'}


def result_view(db, a):
    rows = attempts(db, a['event_id'])
    # Backward compatible: old matches have real team totals, unknown personal kills.
    prior = [r for r in rows if (r['finished_at'], r['run_id']) < (a['finished_at'], a['run_id'])]
    stats = copy.deepcopy(a.get('statistics') or statistics_at_finish(a, prior))
    current = summary(a)
    if current['assisted']:
        stats.update(other_teams=None, event_comparison_status='assisted')
    own = [summary(r) for r in rows if team_id(r) == current['team_id']
           and (r['finished_at'], r['run_id']) <= (a['finished_at'], a['run_id'])]
    return {**stats, **current, 'kill_heatmap':copy.deepcopy((a.get('result') or {}).get('kill_heatmap')),
            'game_complete':a['outcome']=='won' and current['level']==4,
            'history': own[-60:], 'history_total': len(own)}


def public_comparisons(a, rows):
    value=copy.deepcopy(a.get('statistics') or statistics_at_finish(a,rows))
    if a.get('assisted') or a.get('manual_advance'):
        value.update(other_teams=None,event_comparison_status='assisted')
    return value


def validate_statistics(a):
    """Validate portable comparison snapshots without rewriting their baselines."""
    value=a.get('statistics')
    if value is None:return
    if (not isinstance(value,dict) or type(value.get('version')) is not int or value['version']!=1
            or value.get('metric')!='weighted_kill_score' or value.get('team_id')!=team_id(a)
            or value.get('event_comparison_status') not in ('ready','no_peers','assisted')):
        raise ValueError('Invalid result statistics')
    score=a.get('kill_credits',a['kills'])
    for key in ('previous','average','other_teams'):
        c=value.get(key)
        if c is None:continue
        if not isinstance(c,dict):raise ValueError('Invalid result comparison')
        baseline=finite(c.get('baseline'));delta=finite(c.get('delta'),-1000000000)
        integer(c.get('sample_count'),1)
        if not math.isclose(delta,score-baseline):raise ValueError('Invalid result comparison delta')
        if baseline:
            if not math.isclose(finite(c.get('percent'),-100),delta/baseline*100):raise ValueError('Invalid comparison percentage')
        elif c.get('percent') is not None:raise ValueError('Zero baseline has no percentage')
        if key=='other_teams':
            count=integer(c.get('team_count'),2);integer(c.get('rank'),1,count)
            if count!=c['sample_count']+1:raise ValueError('Invalid comparison team count')


class LevelResults:
    def event_results(self, event_id, *, cursor=0, limit=100):
        """Read-only, paged event data. No wallets, calibration or unfinished state."""
        event_id = identifier(event_id)
        cursor, limit = max(0, int(cursor)), max(1, min(100, int(limit)))
        with self.transaction() as db:
            event = db.execute('SELECT data FROM game_events WHERE id=?', (event_id,)).fetchone()
            if not event:
                raise ValueError('event not found')
            rows = attempts(db, event_id)
            selected = rows[cursor:cursor + limit]
            return {'contract': 'photon.event-results', 'version': 1,
                    'event': {'id': event_id, 'name': json.loads(event[0])['name']},
                    'metric': 'weighted_kill_score', 'total': len(rows),
                    'rows': [{**summary(a), 'comparisons_at_finish': public_comparisons(a,rows)} for a in selected],
                    'next_cursor': cursor + limit if cursor + limit < len(rows) else None}
