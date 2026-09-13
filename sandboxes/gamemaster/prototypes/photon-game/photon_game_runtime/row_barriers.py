"""Authoritative row barriers and shared routing, owned by Photon Game."""
from collections import deque
import heapq
import math


def validate_wave_routes(waves, level):
    if level.runtime_version == 1:
        return
    for number, wave in enumerate(waves, 1):
        if (not isinstance(wave, dict) or wave.get('wave') != number
                or not isinstance(wave.get('groups'), list) or not wave['groups']):
            raise ValueError('invalid v2 wave definition')
        for group in wave['groups']:
            weights = group.get('lane_weights') if isinstance(group, dict) else None
            if (not isinstance(weights, dict) or not weights
                    or set(weights) - set(level.enabled_spawn_groups)
                    or any(type(w) not in (int,float) or not math.isfinite(w) or w < 0 for w in weights.values())
                    or not any(w > 0 for w in weights.values())):
                raise ValueError('wave routes must use enabled spawn groups')


def validate_rows(runtime, level):
    """Validate the consumer boundary independently of the Level producer."""
    rows = runtime.get('row_barriers', [])
    if level.runtime_version == 1:
        if rows:
            raise ValueError('row barriers require level runtime v2')
        return []
    if not isinstance(rows, list) or len(rows) != 4:
        raise ValueError('level runtime v2 requires four row barriers')
    identifiers, sockets = set(), set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('invalid row barrier')
        identifier = row.get('row_id')
        members = row.get('socket_ids')
        blocked = row.get('blocked_edges')
        if (not isinstance(identifier, str) or not identifier or identifier in identifiers
                or not isinstance(members, list) or len(members) != 3
                or any(not isinstance(s, str) for s in members)
                or len(set(members)) != 3 or set(members) - level.sockets.keys()
                or sockets.intersection(members)
                or not isinstance(blocked, list) or not blocked
                or any(not isinstance(e, str) for e in blocked)
                or len(set(blocked)) != len(blocked)):
            raise ValueError('invalid row barrier membership or edge IDs')
        try:
            ax, ay, bx, by = (float(row[k]) for k in ('ax', 'ay', 'bx', 'by'))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError('invalid row barrier geometry') from exc
        side = row.get('opening_side')
        if (not all(math.isfinite(v) for v in (ax,ay,bx,by)) or ay != by
                or not 0 < ay < level.height or not 0 <= ax < bx <= level.width
                or side not in ('left','right')
                or (side == 'left' and (ax < 128 or bx != level.width))
                or (side == 'right' and (ax != 0 or level.width - bx < 128))
                or set(blocked) != level.edges_crossed_by_segment(ax,ay,bx,by)):
            raise ValueError('row barrier geometry does not match its blocked roads')
        for member in members:
            socket = level.sockets[member]
            if not ax <= socket['x'] <= bx or abs(socket['y'] - ay) > 56:
                raise ValueError('row socket is outside its barrier band')
        identifiers.add(identifier); sockets.update(members)
    rows = sorted(rows, key=lambda r: r['ay'])
    if [r['opening_side'] for r in rows] != ['right','left','left','right']:
        raise ValueError('invalid row opening order')
    for mask in range(16):
        blocked = {e for i,r in enumerate(rows) if mask & (1 << i) for e in r['blocked_edges']}
        for spawn in level.spawns.values():
            level._shortest_route_with_cost(level._node_id(spawn), blocked)
    for group, row in (('top_outer',rows[0]), ('bottom_outer',rows[-1])):
        spawn = level.spawns.get(group)
        if (spawn is None or spawn['x'] != 0
                or (group == 'top_outer' and spawn['y'] >= row['ay'])
                or (group == 'bottom_outer' and spawn['y'] <= row['ay'])):
            raise ValueError('v2 entrances must be outside the rows on the left')
    return [dict(r, socket_ids=list(r['socket_ids']), blocked_edges=list(r['blocked_edges'])) for r in rows]


class RowBarrierRuntime:
    def _reset_rows(self):
        self.row_topology_revision = 0
        self._row_mask = 0
        self._row_blocked_edges = frozenset()
        self._active_rows = []
        self._row_states = [dict(row_id=r['row_id'], powered=False, active_count=0,
                                 changed_at=None) for r in self.level.row_barriers]
        self._row_reroute_queue = deque()
        self._routing_signature = None
        self._routing_next = {}
        self._routing_distances = {}
        self.row_route_builds = 0

    def _refresh_row_barriers(self):
        mask = 0
        for i, row in enumerate(self.level.row_barriers):
            count = sum(1 for s in row['socket_ids'] if (t := self.placements.get(s))
                        and not t.get('destroyed') and t.get('hp', 0) > 0
                        and self.runtime_time >= float(t.get('activation_complete_at', math.inf)))
            state = self._row_states[i]
            powered = count == 3
            if powered != state['powered']:
                state['changed_at'] = self.runtime_time
                self._event('row_barrier_activated' if powered else 'row_barrier_broken', row_id=row['row_id'])
            state.update(active_count=count, powered=powered)
            if powered:
                mask |= 1 << i
        if mask == self._row_mask:
            return
        self._row_mask = mask
        self.row_topology_revision += 1
        self._active_rows = [r for i,r in enumerate(self.level.row_barriers) if mask & (1 << i)]
        self._row_blocked_edges = frozenset(e for r in self._active_rows for e in r['blocked_edges'])
        self._routing_signature = None
        pending = set(self._row_reroute_queue)
        # Preserve pending order if several turrets die in quick succession.
        # Otherwise the last enemies could be repeatedly pushed to the back.
        waiting = [i for i in self._row_reroute_queue
                   if i in self.enemies and not self.enemies[i]['attacking']]
        self._row_reroute_queue = deque([*waiting, *[e['id'] for e in self.enemies.values()
                                                   if not e['attacking'] and e['id'] not in pending]])

    def _cached_row_route(self, node, penalties=None):
        # One reverse Dijkstra serves every start node and enemy. Memory is
        # bounded to the current topology, including ordinary field wear.
        if penalties is None:
            penalties = self._field_edge_penalties()
        signature = (self._row_mask, tuple(sorted(penalties.items())))
        if signature != self._routing_signature:
            incoming = {}
            for edge in self.level.edge_by_id.values():
                if edge['edge_id'] not in self._row_blocked_edges:
                    incoming.setdefault(edge['to'], []).append(edge)
            core = self.level._node_id(self.level.core)
            distances, following, queue = {core: 0.0}, {}, [(0.0, core)]
            while queue:
                cost, dest = heapq.heappop(queue)
                if cost != distances[dest]:
                    continue
                for edge in incoming.get(dest, ()):
                    candidate = cost + edge['cost'] + penalties.get(edge['edge_id'], 0)
                    source = edge['from']
                    if candidate < distances.get(source, math.inf):
                        distances[source], following[source] = candidate, edge
                        heapq.heappush(queue, (candidate, source))
            self._routing_signature = signature
            self._routing_distances, self._routing_next = distances, following
            self.row_route_builds += 1
        if node not in self._routing_distances:
            return None
        edges, cursor = [], node
        while cursor in self._routing_next:
            edge = self._routing_next[cursor]
            edges.append(edge); cursor = edge['to']
        return edges, self._routing_distances[node]

    def _row_prefix_clear(self, points):
        for a,b in zip(points, points[1:]):
            for row in self._active_rows:
                y = row['ay']
                if (a[1] - y) * (b[1] - y) < 0:
                    x = a[0] + (b[0]-a[0]) * (y-a[1]) / (b[1]-a[1])
                    if row['ax'] <= x <= row['bx']:
                        return False
        return True

    def _reroute_row_enemy(self, enemy, *, force_field_contact=False, edge_penalties=None):
        if enemy['attacking']:
            return False
        tracking = self._sync_enemy_road_edge(enemy, search_all=True)
        if tracking is None:
            return False
        edge, (px,py,index,_,progress,_) = tracking
        origin = (enemy['x'],enemy['y'])
        options = []
        if edge_penalties is None:
            edge_penalties = self._field_edge_penalties()
        # Continue to either reachable endpoint along the current road. A
        # newly closed edge may be exited on the enemy's current side only.
        for reverse, node, partial in (
            (False, edge['to'], edge['points'][index+1:]),
            (True, edge['from'], list(reversed(edge['points'][:index+1]))),
        ):
            prefix = [origin,(px,py),*partial]
            if not self._row_prefix_clear(prefix):
                continue
            result = self._cached_row_route(node, edge_penalties)
            if result is None:
                continue
            onward, cost = result
            length = sum(math.dist(a,b) for a,b in zip(prefix,prefix[1:]))
            # Prefer continuing forward when distances tie.
            options.append((cost+length, reverse, prefix, onward))
        if not options:
            return False
        if force_field_contact:
            reversals = [option for option in options if option[1]]
            if reversals:
                options = reversals
        _, reverse, prefix, onward = min(options, key=lambda x: x[:2])
        points = []
        for point in [*prefix, *self.level._points_for_edges(onward)]:
            point = tuple(point)
            if not points or point != points[-1]:
                points.append(point)
        if len(points) < 2:
            return False
        path = self._path_to_core_basin(enemy['lane'], enemy['track'], enemy['collision_radius'], points=points)
        # Do not round the initial turn back toward an endpoint: keep the
        # first point at the actual position, never move the particle here.
        enemy.update(path=path, segment=0, progress=0.0,
                     route_steps=[dict(edge_id=edge['edge_id'], reverse=reverse),
                                  *[dict(edge_id=e['edge_id'], reverse=False) for e in onward]],
                     current_route_step=0, current_edge_id=edge['edge_id'],
                     current_edge_progress=progress, row_route_revision=self.row_topology_revision)
        if force_field_contact:
            slow = float(self.settings['force_field_slow']) * (-1 if reverse else 1)
            enemy['vx'] *= slow; enemy['vy'] *= slow
            self._event('orc_rerouted', enemy_id=enemy['id'], edge_id=edge['edge_id'],
                        node_id=edge['from'] if reverse else edge['to'],
                        edge_progress=round(progress,4))
        return True

    def _reroute_rows_batch(self):
        if not self._row_reroute_queue:
            return
        penalties = self._field_edge_penalties()
        for _ in range(min(48, len(self._row_reroute_queue))):
            enemy = self.enemies.get(self._row_reroute_queue.popleft())
            if enemy is not None and not enemy['attacking']:
                if not self._reroute_row_enemy(enemy, edge_penalties=penalties):
                    self._row_reroute_queue.append(enemy['id'])

    def _clip_row_motion(self, enemy, origin):
        """Swept expanded rectangles prevent tunnelling and crowd leakage."""
        if enemy['attacking']:
            return
        x,y = origin
        pad = enemy['collision_radius'] + 3.0
        for row in self._active_rows:
            left,right = row['ax']-pad,row['bx']+pad
            top,bottom = row['ay']-pad,row['by']+pad
            nx,ny = enemy['x'],enemy['y']
            if ((y < top and ny < top) or (y > bottom and ny > bottom)
                    or (x < left and nx < left) or (x > right and nx > right)):
                continue
            if left < x < right and top < y < bottom:
                # A barrier powered up through this body. Resolve the small
                # overlap on its existing side, allowing motion away.
                if y <= row['ay']:
                    if ny > top: enemy['y'] = top
                elif ny < bottom: enemy['y'] = bottom
                continue
            enter, leave, axis = 0.0, 1.0, None
            for a,d,lo,hi,name in ((x,nx-x,left,right,'x'),(y,ny-y,top,bottom,'y')):
                if abs(d) < 1e-12:
                    if not lo < a < hi: leave = -1.0; break
                    continue
                first,last = sorted(((lo-a)/d,(hi-a)/d))
                if first >= enter: enter,axis = first,name
                leave = min(leave,last)
            if axis is not None and 0 <= enter < leave and enter <= 1:
                t = max(0, enter-1e-6)
                enemy['x'],enemy['y'] = x+(nx-x)*t,y+(ny-y)*t
                enemy['v'+axis] = 0.0
