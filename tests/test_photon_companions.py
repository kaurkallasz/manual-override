"""L4 companion gameplay and contract checks; no live game or hardware."""
import copy
import json
import math
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from test_photon_framework import load, ROOT, legacy_level_bundle

TRACKS = ('damage-machine-gun', 'damage-flamethrower', 'damage-mortar', 'damage-tesla-coil', 'forcefield')
MIDDLE = {'socket_08', 'socket_09', 'socket_11', 'socket_15'}


class CompanionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.level = load('photon-level')
        cls.game = load('photon-game')
        cls.bundle = cls.level.runtime_bundle()
        cls.helpers = sys.modules[cls.game.DefenseEngine.__module__].companions

    def engine(self, tier=4, runtime=None):
        e = self.game.DefenseEngine(runtime or self.bundle['runtime'], self.bundle['waves'])
        e.set_virtual_play(True)
        e.set_virtual_test_loadout(dict.fromkeys(TRACKS, tier))
        return e

    def test_all_sockets_weapons_and_levels(self):
        for level in range(1, 5):
            for atom in range(100, 104):
                e = self.engine(level)
                for sid in e.level.sockets:
                    e.place(atom, sid, source='virtual')
                state = e.snapshot()
                with self.subTest(level=level, atom=atom):
                    self.assertEqual(len(state['towers']), 16)
                    self.assertEqual(len(state['companions']), 12 if level == 4 else 0)
                    self.assertFalse(MIDDLE & {c['socket_id'] for c in state['companions']})
                    self.assertEqual(len({c['placement_id'] for c in state['companions']}), len(state['companions']))

    def test_descriptor_positions_and_invalid_inputs(self):
        runtime = self.bundle['runtime']
        for sid, socket in runtime['sockets'].items():
            d = socket['companion']
            self.assertEqual(d['eligible'], sid not in MIDDLE)
            if d['eligible']:
                self.assertAlmostEqual(d['x'], 2*socket['marker_x']-socket['x'])
                self.assertEqual(d['y'], socket['y'])
                self.assertEqual(d['visual_y'], socket['marker_y'])
        for change in ({'pod_size':112}, {'x':float('nan')}, {'visual_x':643}, {'eligible':1}, {'version':True}):
            malformed = copy.deepcopy(runtime)
            malformed['sockets']['socket_01']['companion'].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.engine(runtime=malformed)

    def test_older_level_without_descriptors(self):
        runtime = copy.deepcopy(self.bundle['runtime'])
        for socket in runtime['sockets'].values(): socket.pop('companion')
        e = self.engine(runtime=runtime)
        e.place(100, 'socket_01', source='virtual')
        self.assertEqual(e.snapshot()['companions'], [])
        old = legacy_level_bundle()
        e = self.game.DefenseEngine(old['runtime'], old['waves'])
        self.assertEqual(e.snapshot()['companions'], [])

    def test_upgrade_downgrade_aim_and_idempotence(self):
        e = self.engine(3); e.place(100, 'socket_01', source='virtual')
        t = e.placements['socket_01']; t['hp'] *= .4; t['cooldown'] = .12
        e.runtime_time = 20
        e.set_virtual_test_loadout(dict.fromkeys(TRACKS, 4))
        c = t['companion']; c['cooldown'] = .09
        self.assertEqual(c['activation_complete_at'], 23)
        self.assertAlmostEqual(t['hp']/t['max_hp'], .4)
        e.set_virtual_test_loadout(dict.fromkeys(TRACKS, 4))
        self.assertIs(t['companion'], c)
        self.assertEqual(c['cooldown'], .09); self.assertEqual(t['cooldown'], .12)
        e.set_tower_aim(100, angle_degrees=110, spread=.7, socket_id='socket_01')
        state = e.snapshot()
        self.assertEqual(state['companions'][0]['targeting']['angle'], state['towers'][0]['targeting']['angle'])
        e.set_virtual_test_loadout(dict.fromkeys(TRACKS, 3))
        self.assertEqual(e.snapshot()['companions'], [])
        e.reset(); self.assertEqual(e.snapshot()['companions'], [])

    def test_shared_health_destruction_and_replacement(self):
        e = self.engine(); e.place(100, 'socket_01', source='virtual')
        t = e.placements['socket_01']; c = t['companion']; before = t['hp']
        e._damage_towers([{'id':1, 'x':c['x'], 'y':c['y'], 'tower_dps':50}], .2)
        self.assertAlmostEqual(t['hp'], before-10)
        self.assertEqual(e.snapshot()['companions'][0]['hp'], t['hp'])
        t['hp'] = 1
        e._damage_towers([{'id':1, 'x':c['x'], 'y':c['y'], 'tower_dps':50}], .2)
        self.assertTrue(t['destroyed'])
        self.assertTrue(e.snapshot()['companions'][0]['destroyed'])
        e.place(100, 'socket_01', source='virtual')
        self.assertIsNot(e.placements['socket_01']['companion'], c)
        self.assertFalse(e.snapshot()['companions'][0]['destroyed'])
        t=e.placements['socket_01'];t['hp']=1
        e.place(100, 'socket_01', source='virtual')
        self.assertEqual(e.snapshot()['companions'][0]['hp'], t['max_hp'])

    def test_contact_union_does_not_double_damage(self):
        fraction = self.helpers.contact_fraction
        self.assertEqual(fraction(0,0,0,0,[(0,0,10),(1,0,10)]), 1)
        self.assertAlmostEqual(fraction(-20,0,20,0,[(-2,0,10),(2,0,10)]), .6)
        self.assertAlmostEqual(fraction(-20,0,20,0,[(-12,0,4),(12,0,4)]), .4)
        self.assertEqual(fraction(0,20,5,20,[(0,0,10),(1,0,10)]), 0)

    def test_independent_weapon_fire_and_mortar_origin(self):
        for atom in range(100,104):
            e=self.engine();e.place(atom,'socket_01',source='virtual');e.runtime_time=e.sim_time=10
            t=e.placements['socket_01'];t['aim_angle']=0;t['aim_spread']=.5
            c=e._sync_companions()[0]
            enemies={}
            for i,unit in enumerate((t,c),1):
                targeting=e._tower_targeting(unit)
                if atom==102: x,y=targeting['target_x'],targeting['target_y']
                elif atom==101: x,y=e._flamethrower_path(unit, targeting)[4]
                else:x,y=unit['x']+25,unit['y']
                enemies[i]={'id':i,'x':x,'y':y,'hp':10000,'progress':i}
            e.enemies=enemies
            e._fire_towers(2,set())
            with self.subTest(atom=atom):
                self.assertEqual(t['last_fire_at'],10)
                self.assertEqual(c['last_fire_at'],10)
                self.assertGreater(c['cooldown'],0)
                if atom==102:
                    self.assertEqual(len(e.pending_mortar_rounds),2)
                    self.assertEqual(e.pending_mortar_rounds[1]['tower_id'],c['placement_id'])
                    self.assertEqual(e.pending_mortar_rounds[1]['origin_x'],c['x'])
                    e.set_virtual_test_loadout(dict.fromkeys(TRACKS,3))
                    self.assertEqual(len(e.pending_mortar_rounds),2)
                    e.sim_time=12;e._resolve_mortar_rounds(set())
                    self.assertEqual(len(e.pending_mortar_rounds),0)
                else:self.assertTrue(any(enemy['hp']<10000 for enemy in enemies.values()))

    def test_activation_and_topology_remain_parent_owned(self):
        e=self.engine()
        for sid in ('socket_01','socket_03','socket_05'):e.place(100,sid,source='virtual')
        e.runtime_time=1
        c=e.placements['socket_01']['companion']
        e.enemies={1:{'id':1,'x':c['x']+25,'y':c['y'],'hp':1,'progress':1}}
        e._fire_towers(1,set());self.assertIsNone(c['last_fire_at'])
        e.enemies.clear()
        before=e.snapshot()
        e.set_virtual_test_loadout(dict.fromkeys(TRACKS,3))
        after=e.snapshot()
        self.assertEqual(before['activation_order'], after['activation_order'])
        self.assertEqual(before['row_barriers'],after['row_barriers'])
        self.assertEqual([t['linked_turret_count'] for t in before['towers']], [t['linked_turret_count'] for t in after['towers']])
        self.assertEqual([(f['from_socket'],f['to_socket']) for f in before['connections']],[(f['from_socket'],f['to_socket']) for f in after['connections']])

    def test_physical_l4_profile_and_input_mode(self):
        e=self.engine();e.set_virtual_play(False)
        e.player_progression={'green':{'control_tier':1,'levels':dict.fromkeys(TRACKS,4)}}
        e.place(100,'socket_01',source='physical',team='green')
        self.assertEqual(len(e.snapshot()['companions']),1)
        e.start(progression=e.player_progression)
        self.assertEqual(len(e.snapshot()['companions']),1)
        self.assertEqual(e.snapshot()['companion_policy']['version'],1)

    def test_pair_kill_is_counted_once(self):
        e=self.engine();e.place(100,'socket_01',source='virtual');e.start()
        e.runtime_time=10
        t=e.placements['socket_01'];t['aim_angle']=0;t['cooldown']=0;t['companion']['cooldown']=0
        e._spawn_enemy('grunt', {})
        enemy=next(iter(e.enemies.values()))
        enemy.update(x=t['x']+30,y=t['y'],hp=1)
        # Hold this known target in both cones while exercising the real step,
        # weapon fire, enemy removal and authoritative score increment.
        with patch.object(e,'_spawn_due'), patch.object(e,'_integrate_particles'):
            e.step(.01)
        self.assertEqual(e.kills,1)
        self.assertNotIn(enemy['id'],e.enemies)

    def test_edited_companion_overlap_is_rejected_before_save(self):
        path=ROOT/'sandboxes/gamemaster/prototypes/photon-level/assets/tiled/levels/z-pixel-first-map.tmj'
        source=json.loads(path.read_text())
        for ref in source['tilesets']:ref['source']=str((path.parent/ref['source']).resolve())
        layout=sys.modules['level_layout']
        with tempfile.TemporaryDirectory() as folder:
            candidate=Path(folder)/'test.tmj';candidate.write_text(json.dumps(source))
            before=candidate.read_bytes()
            submitted=layout.socket_records(source)
            next(s for s in submitted if s['socket_id']=='socket_04')['x']+=10
            with self.assertRaisesRegex(ValueError,'companion.*overlaps'):
                layout.update_socket_layout_file(candidate,submitted,validate_candidate=self.level.parse_tiled_level)
            self.assertEqual(candidate.read_bytes(),before)


if __name__ == '__main__': unittest.main()
