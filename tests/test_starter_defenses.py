"""Atom homes and one-use starter weapons; no live hardware or player data."""
import copy
import json
import unittest
from unittest.mock import patch
from test_photon_framework import load, PROTOTYPES
import test_event_game as event_fixture

TRACKS = ('damage-machine-gun', 'damage-flamethrower', 'damage-mortar', 'damage-tesla-coil')


class StarterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = load('photon-level').runtime_bundle()
        cls.game = load('photon-game')

    def engine(self, level=1, selected=(100, 102), upgrades=(1, 2, 3, 4)):
        e = self.game.DefenseEngine(self.bundle['runtime'], self.bundle['waves'])
        e.set_virtual_play(True)
        saved = {'level': level, 'atoms': {side: {'tag': tag} for side, tag in zip(('green', 'purple'), selected)}}
        players = {side: {'control_tier': level, 'levels': dict(zip(TRACKS, upgrades))} for side in ('green', 'purple')}
        e.start(event_game=saved, progression=players)
        return e

    def test_level_visibility_selected_weapon_and_upgrades(self):
        for level in range(1, 5):
            for selected in ((100, 102), (101, 103)):
                e = self.engine(level, selected)
                state = e.snapshot()
                expected = set(range(100, 104)) if level == 4 else set(selected)
                self.assertEqual({h['atom_tag_id'] for h in state['home_platforms']}, expected)
                self.assertEqual({t['atom_tag_id'] for t in state['starter_turrets']}, expected)
                self.assertTrue(all(t['operational'] and not t['rebuildable'] for t in state['starter_turrets']))
                for t in state['starter_turrets']:
                    self.assertEqual(t['tower_type'], e.piece_roles[t['atom_tag_id']])
                    self.assertEqual(t['upgrade_level'], t['atom_tag_id']-99)
                    self.assertAlmostEqual(t['max_hp'], e._tower_max_hp()*t['upgrade_multiplier']*e._link_multiplier_for_count(1))
                    self.assertEqual(e.mobile_arms[t['owner']].tags[t['atom_tag_id']], next({k:h[k] for k in ('x','y')} for h in state['home_platforms'] if h['id']==t['socket_id']))
                self.assertEqual(state['companions'], [])
                self.assertEqual(state['activation_order'], [])
                self.assertEqual(state['towers'], [])
                self.assertEqual(state['core_sequence']['ring_candidate_count'], 0)
                self.assertFalse(e._active_rows)

    def test_permanent_destruction_all_activation_paths_and_new_match(self):
        e = self.engine(4)
        t = e.starter_turrets['starter_green_1']; identity = t['aim_instance']
        e._damage_towers([{'id': 999, 'enemy_type':'grunt', 'x':t['x'], 'y':t['y'], 'tower_dps':t['hp']*2}], 1)
        self.assertTrue(t['destroyed']); self.assertEqual(t['hp'], 0)
        for action in (lambda:e.place(100,t['socket_id'],source='virtual'),
                       lambda:e.place(100,t['socket_id'],source='physical'),
                       lambda:e.operator_turret_command('operator_atom',t['socket_id'],100),
                       lambda:e.operator_turret_command('operator_turret',t['socket_id'],'green'),
                       lambda:e._replenish_tower(t,100),
                       lambda:e._replace_tower(t,100,'machine_gun','green','operator')):
            with self.assertRaises(ValueError):action()
        e.remove_atom(100,source='virtual')
        e.place(100,'socket_01',source='virtual')
        self.assertEqual(t['hp'],0)
        e.set_virtual_play(False);e.set_virtual_play(True);e._refresh_upgrade_levels()
        for _ in range(3):
            record=next(x for x in e.snapshot()['starter_turrets'] if x['socket_id']==t['socket_id'])
            self.assertEqual(record['aim_instance'],identity)
            self.assertTrue(record['destroyed']);self.assertFalse(record['operational'])
        e.reset();e.start(event_game={'level':4,'atoms':{'green':{'tag':100},'purple':{'tag':102}}})
        fresh=e.starter_turrets['starter_green_1']
        self.assertNotEqual(fresh['aim_instance'],identity);self.assertGreater(fresh['hp'],0)

    def test_all_weapons_fire_and_mortar_keeps_its_launch_origin(self):
        for tag in range(100,104):
            e=self.engine(4);e.runtime_time=e.sim_time=10
            t=next(t for t in e.starter_turrets.values() if t['atom_tag_id']==tag)
            e.starter_turrets={t['socket_id']:t}
            t['aim_angle']=0;t['aim_spread']=.5
            targeting=e._tower_targeting(t)
            if tag==102:x,y=targeting['target_x'],targeting['target_y']
            elif tag==101:x,y=e._flamethrower_path(t,targeting)[4]
            else:x,y=t['x']+25,t['y']
            enemy={'id':1,'x':x,'y':y,'hp':10000,'progress':1}
            e.enemies={1:enemy};e._fire_towers(2,set())
            self.assertEqual(t['last_fire_at'],10)
            if tag==102:
                shot=e.pending_mortar_rounds[0]
                self.assertEqual((shot['origin_x'],shot['origin_y']),(t['x'],t['y']))
                self.assertEqual(shot['origin_pod_size'],72)
                e._apply_tower_damage(t,t['hp']);e.sim_time=12;e._resolve_mortar_rounds(set())
            self.assertLess(enemy['hp'],10000)

    def test_ranged_attacks_can_destroy_starters(self):
        e=self.engine();t=e.starter_turrets['starter_green_1'];e.ranged.geometry()
        target=e.ranged.targets[t['socket_id']+':primary']
        self.assertEqual(target['radius'],36)
        e.ranged.arrows=[dict(id=1,enemy_id=1,target=dict(target),origin_x=t['x']-60,origin_y=t['y'],
                             target_x=t['x'],target_y=t['y'],launch_at=0,impact_at=1,damage=t['hp'],progress=0)]
        e.sim_time=2;e.ranged.advance_arrows()
        self.assertTrue(t['destroyed']);self.assertEqual(e.ranged.stats['tower_destructions'],1)
        self.assertNotIn(t['socket_id']+':primary',e.ranged.targets)

    def test_kill_scoring_uses_the_normal_owner_and_death_path(self):
        e=self.engine();t=e.starter_turrets['starter_green_1'];e.starter_turrets={t['socket_id']:t}
        e.runtime_time=10;t['aim_angle']=0;t['aim_spread']=1
        e._spawn_enemy('grunt',{})
        enemy=next(iter(e.enemies.values()));enemy.update(x=t['x']+20,y=t['y'],hp=1)
        with patch.object(e,'_spawn_due'),patch.object(e,'_integrate_particles'):
            e.step(.05);e.step(.05)
        self.assertEqual(e.kills,1)
        self.assertEqual(e.rewards.combat['grunt'],1)

    def test_platforms_are_on_the_inward_edges_and_old_overlay_is_absent(self):
        homes=self.bundle['runtime']['atom_homes']
        for h in homes:
            left,right,top,bottom=(1360,1496,736,864) if h['owner']=='green' else (300,372,96,224)
            self.assertGreaterEqual(h['x']-h['size']/2,left)
            self.assertLessEqual(h['x']+h['size']/2,right)
            self.assertGreaterEqual(h['y']-h['size']/2,top)
            self.assertLessEqual(h['y']+h['size']/2,bottom)
            self.assertLess(h['turret_x'],h['x'])
        kinds={i['kind'] for layer in self.bundle['runtime']['visual_scene']['layers'] for i in layer['items']}
        self.assertFalse({'activation_zone','atom_start'} & kinds)
        self.assertEqual(len(self.bundle['runtime']['sockets']),16)

    def test_bad_geometry_and_legacy_levels(self):
        for mutation in ({'x':float('nan')},{'turret_y':-10},{'slot':True},{'owner':'unknown'}):
            r=copy.deepcopy(self.bundle['runtime']);r['atom_homes'][0].update(mutation)
            with self.assertRaises(ValueError):self.game.DefenseEngine(r,self.bundle['waves'])
        r=copy.deepcopy(self.bundle['runtime']);r.pop('atom_homes')
        e=self.game.DefenseEngine(r,self.bundle['waves']);e.start()
        self.assertEqual(e.snapshot()['starter_turrets'],[])

    def test_authoring_rejects_home_marker_collisions(self):
        import tempfile
        from pathlib import Path
        level=load('photon-level')
        path=PROTOTYPES/'photon-level/assets/tiled/levels/z-pixel-first-map.tmj'
        data=json.loads(path.read_text())
        home=next(obj for layer in data['layers'] for obj in layer.get('objects',[]) if obj.get('type')=='AtomHome')
        socket=self.bundle['runtime']['sockets']['socket_01']
        home.update(x=socket['marker_x']-28,y=socket['marker_y']-28)
        for tileset in data['tilesets']:tileset['source']=str((path.parent/tileset['source']).resolve())
        with tempfile.TemporaryDirectory() as folder:
            candidate=Path(folder)/'bad.tmj';candidate.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'overlap'):level.parse_tiled_level(candidate)


class StarterApiTests(unittest.TestCase):
    setUp = event_fixture.EventGameTests.setUp
    command = event_fixture.EventGameTests.command
    start = event_fixture.EventGameTests.start
    def test_preview_choice_start_upgrades_and_reconnect(self):
        self.g._engine.stop_background()
        initial=self.g.game_snapshot()
        self.assertEqual([h['atom_tag_id'] for h in initial['home_platforms']],[100,102])
        r=self.command('starting_atom',side='green',atom_tag_id=101)
        self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(self.g.game_snapshot()['home_platforms'][0]['atom_tag_id'],101)
        self.assertTrue(all(t['preview'] for t in self.g.game_snapshot()['starter_turrets']))
        # The phone countdown starts without repeating the GM's chosen Atoms.
        r=self.command('start')
        self.assertEqual(r.status_code,200,r.json)
        t=self.g._engine.starter_turrets['starter_green_1']
        self.assertEqual(t['tower_type'],'flamethrower')
        self.assertEqual(self.command('starting_atom',side='green',atom_tag_id=100).status_code,400)
        self.g._engine._apply_tower_damage(t,t['hp'])
        for _ in range(2):
            r=self.c.get('/s/gamemaster/p/laser-tag-y/api/state')
            self.assertTrue(next(t for t in r.json['starter_turrets'] if t['socket_id']=='starter_green_1')['destroyed'])
        self.assertEqual(self.command('end_match').status_code,200)
        self.assertEqual(self.command('unlock_next_level').status_code,200)
        self.assertEqual(self.command('next_match').status_code,200)
        r=self.command('start',starting_atoms={'green':101,'purple':102})
        self.assertEqual(r.status_code,200,r.json)
        t=self.g._engine.starter_turrets['starter_green_1']
        self.assertEqual(t['upgrade_level'],2);self.assertFalse(t['destroyed'])

    def test_mobile_owner_can_aim_starter_but_cannot_aim_enemy_or_dead_unit(self):
        self.g._engine.stop_background();self.start()
        t=self.g._engine.starter_turrets['starter_green_1']
        data={k:t[k] for k in ('socket_id','atom_tag_id','aim_instance','aim_revision','activation_started_at')}
        data.update(side='green',run_id=self.g._run_id,angle_degrees=140,spread=.7)
        result=self.g.mobile_turret_aim(data)
        self.assertAlmostEqual(result['targeting']['angle_degrees'],140)
        with self.assertRaises(ValueError):self.g.mobile_turret_aim({**data,'side':'purple','aim_revision':t['aim_revision']})
        self.g._engine._apply_tower_damage(t,t['hp'])
        with self.assertRaises(ValueError):self.g.mobile_turret_aim({**data,'aim_revision':t['aim_revision']})

    def test_home_defaults_need_no_marker_placement_and_camera_selection_stays_explicit(self):
        self.g._engine.stop_background()
        with patch.object(self.g,'starting_atoms',wraps=self.g.starting_atoms) as resolve:
            r=self.command('start')
            self.assertEqual(r.status_code,200,r.json)
            self.assertEqual(resolve.call_args.args[3],{'green':100,'purple':102})

    def test_automatic_selection_keeps_preview_valid_and_rejects_invalid_inputs(self):
        self.g._engine.stop_background()
        r=self.command('starting_atom',side='green',atom_tag_id=None)
        self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(self.g.game_snapshot()['home_platforms'][0]['atom_tag_id'],100)
        with patch.object(self.g,'starting_atoms',side_effect=ValueError('camera needs an Atom')) as resolve:
            r=self.command('start')
            self.assertEqual(r.status_code,400)
            self.assertIsNone(resolve.call_args.args[3]['green'])
        self.assertEqual(self.command('start',starting_atoms=[]).status_code,400)


if __name__=='__main__':unittest.main()
