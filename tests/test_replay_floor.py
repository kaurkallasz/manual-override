"""Saved authored field artwork, using the same geometry as the kill overlay."""
import copy
import unittest
from test_photon_framework import load


class ReplayFloorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.level = load('photon-level')
        cls.game = load('photon-game')
        cls.progress = load('photon-progress')

    def setUp(self):
        self.bundle = self.level.runtime_bundle()
        self.engine = self.game.DefenseEngine(self.bundle['runtime'], self.bundle['waves'])
        self.validate = self.progress.ProgressStore.record.__globals__['validate_heatmap']

    def test_saved_floor_matches_authored_layers_and_published_artwork(self):
        heatmap = self.engine.rewards.heatmap.snapshot()
        floor = heatmap['floor']
        self.validate(heatmap, 0, 0)
        self.assertEqual(floor['revision'], self.bundle['revision'])
        authored = [item for layer in self.bundle['runtime']['visual_scene']['layers']
                    for item in layer['items'] if item['kind'] == 'sprite']
        recorded = [item for layer in floor['layers'] for item in layer['items']]
        self.assertEqual(recorded, authored)
        for key, path in floor['assets'].items():
            self.assertEqual(path, self.bundle['presentation']['assets']['map/' + key])
            self.assertNotIn('camera', path)
        # Layout/consumer mutations cannot rewrite a run's saved image recipe.
        self.bundle['runtime']['replay_floor']['layers'].clear()
        self.assertEqual(self.engine.rewards.heatmap.snapshot()['floor'], floor)
        floor['layers'].clear()
        self.assertTrue(self.engine.rewards.heatmap.snapshot()['floor']['layers'])

    def test_unavailable_artwork_has_no_invented_floor(self):
        from unittest.mock import patch
        with patch.object(self.level, '_runtime_asset_cache', {'status': 'unavailable'}):
            self.assertIsNone(self.level.runtime_bundle()['runtime']['replay_floor'])
        h = self.engine.rewards.heatmap.snapshot()
        del h['floor']
        self.validate(h, 0, 0)

    def test_import_rejects_external_paths_invalid_transforms_and_unbounded_scenes(self):
        original = self.engine.rewards.heatmap.snapshot()
        key = next(iter(original['floor']['assets']))
        changes = [
            lambda f: f['assets'].update({key: 'https://example.com/image.png'}),
            lambda f: f['assets'].update({key: '../private.png?v=' + 'a' * 64}),
            lambda f: f['layers'][0].update(opacity=2),
            lambda f: f['layers'][0]['items'][0].update(origin_x=float('nan')),
            lambda f: f['layers'][0]['items'][0].update(width=0),
            lambda f: f['layers'][0]['items'][0].update(source=[0, 0, -1, 10]),
            lambda f: f['layers'][0]['items'][0].update(asset_id='missing'),
            lambda f: f['layers'][0]['items'][0].update(asset_id={}),
            lambda f: f.update(layers=f['layers'] * 65),
        ]
        for change in changes:
            h = copy.deepcopy(original);change(h['floor'])
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.validate(h, 0, 0)


if __name__ == '__main__':
    unittest.main()
