"""Smoke-test exported Kling stills: run after build_turret_kling_keyframes.py.

Run with the bundled Python: python -m unittest discover -s tests
-p test_turret_kling_keyframes.py
"""

import json
from pathlib import Path
import unittest

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "assets/game-art/z-pixel-v2"


class ElevatorKeyframeSmokeTest(unittest.TestCase):
    def test_exported_stills_and_three_second_timeline(self):
        manifest = json.loads((PACK / "kling-turret-install-keyframes.json").read_text())
        self.assertEqual(manifest["duration_s"], 3)
        self.assertEqual(len(manifest["assets"]), 4)
        self.assertEqual(len({a["first_frame"] for a in manifest["assets"]}), 1)
        frames = []
        for stage in manifest["timeline"]:
            start, end = stage["frames"]
            frames.extend(range(start, end + 1))
            self.assertEqual(stage["time_s"], [start / 24, (end + 1) / 24])
        self.assertEqual(frames, list(range(72)))
        self.assertEqual(manifest["timeline"][-1]["frames"], [66, 71])

        for asset in manifest["assets"]:
            for master_key, upload_key in (("first_frame", "first_upload"),
                                           ("last_frame", "last_upload")):
                with Image.open(ROOT / asset[master_key]) as master:
                    self.assertEqual(master.mode, "RGBA")
                    self.assertEqual(master.size, (1024, 1024))
                    alpha = master.getchannel("A")
                    self.assertEqual(alpha.getbbox(), (64, 64, 960, 960))
                    self.assertEqual(alpha.crop((0, 0, 1024, 64)).getextrema(), (0, 0))
                    self.assertEqual(alpha.crop((0, 960, 1024, 1024)).getextrema(), (0, 0))
                    self.assertEqual(alpha.crop((0, 0, 64, 1024)).getextrema(), (0, 0))
                    self.assertEqual(alpha.crop((960, 0, 1024, 1024)).getextrema(), (0, 0))
                    if master_key == "first_frame":
                        # Protect the black shaft from accidental global black keying.
                        self.assertEqual(master.getpixel((512, 512)), (0, 0, 0, 255))
                        self.assertEqual(alpha.crop((491, 467, 533, 548)).getextrema(),
                                         (255, 255))
                    with Image.open(ROOT / asset[upload_key]) as upload:
                        self.assertEqual(upload.mode, "RGB")
                        self.assertEqual(upload.size, master.size)
                        self.assertEqual(upload.getpixel((0, 0)), (0, 0, 0))
                        self.assertEqual(upload.getpixel((512, 512)),
                                         master.getpixel((512, 512))[:3])


if __name__ == "__main__":
    unittest.main()
