"""Run: .venv/bin/python -m unittest discover -s tests -p 'test_photon_board_tracking.py'.

All robot/camera inputs are fixtures. No test opens a camera or sends commands.
"""

import copy
import json
import subprocess
import shutil
import sys
import tempfile
import time
import unittest

from test_photon_framework import FakeContext, PROTOTYPES, load
from flask import Flask

sys.path.insert(0, str(PROTOTYPES / "photon-board"))
sys.path.insert(0, str(PROTOTYPES / "auto-pickup-game"))
from board_tracking import BoardTracker, PhysicalPlacementTracker
from tracking_output import CalibrationProjection, IntentStore


def calibration():
    samples = [(0.1, 0.1), (0.5, 0.1), (0.9, 0.1), (0.1, 0.9), (0.5, 0.9), (0.9, 0.9)]
    arm = {"points": {str(i): {"camera": {"u": u, "v": v},
        "pose": {"x": u * 500, "y": v * 500, "set": True}} for i, (u, v) in enumerate(samples)},
        "pickup_height": 0, "stack_drop_offset": 31.5,
        "parallax_points": {str(i): {"ground": {"u": u, "v": v}, "raised": {"u": u + .02, "v": v}}
            for i, (u, v) in enumerate([(0.1, .1), (.9, .1), (.1, .9), (.9, .9)])}}
    return {"arms": {"green": copy.deepcopy(arm), "purple": copy.deepcopy(arm)}}


def tag(tag_id, u, v):
    return {"id": tag_id, "nx": u, "ny": v, "missing": 0, "tracked": True}


def arm(pose, now=100, pump="off"):
    return {"connected": True, "enabled": True, "pose": list(pose), "target": [350, 250, 1],
            "pump_mode": pump, "feedback_at": now, "control_mode": "cartesian"}


class TrackingTests(unittest.TestCase):
    def setUp(self):
        self.tracker = BoardTracker()
        self.projector = CalibrationProjection(calibration())
        self.now = 100.0
        self.tags = [tag(100, .32, .3), tag(101, .75, .25), tag(40, .7, .5)]
        self.arms = {"green": arm([150, 150, 0]), "purple": arm([50, 450, 0])}

    def sample(self, *, advance=.2, frame=None, status="ready", projection=True, intents=None):
        self.now += advance
        for value in self.arms.values():
            value["feedback_at"] = self.now
        runtime = {"status": status, "source": "camera", "frame_at": self.now if frame is None else frame,
            "width": 1600, "height": 900, "visible_ids": [t["id"] for t in self.tags],
            "detections": copy.deepcopy(self.tags), "arms": copy.deepcopy(self.arms), "inputs": {}, "errors": []}
        remembered = {key: rec["tag"] for key, rec in self.tracker.records.items()}
        remembered.update({t["id"]: t for t in self.tags})
        projected = self.projector.project(list(remembered.values()), self.arms) if projection else None
        return self.tracker.update(runtime, projected, intents, self.now)

    def row(self, result, tag_id=100):
        return next(row for row in result["tags"] if row["id"] == tag_id)

    def test_unique_candidate_has_ltx_style_metric_values(self):
        output = self.sample()
        green = output["arms"]["green"]
        self.assertEqual(green["considered_tag"], 100)
        self.assertEqual(green["candidates"][0]["xy_mm"], 0)
        self.assertEqual(green["candidates"][0]["fill"], 100)
        self.assertEqual(self.row(output)["stage"], "near_arm")
        self.assertEqual(green["command_distance"]["xy_mm"], 223.6)

    def test_ambiguous_and_two_arm_competition_never_bind(self):
        self.tags.append(tag(102, .34, .3))
        result = self.sample()
        self.assertTrue(result["arms"]["green"]["ambiguous"])
        self.assertIsNone(result["arms"]["green"]["considered_tag"])
        self.tags.pop()
        self.arms["purple"] = arm([150, 150, 0])
        result = self.sample()
        for value in result["arms"].values():
            self.assertTrue(value["ambiguous"])
            self.assertIsNone(value["considered_tag"])

    def test_pickup_carry_release_and_stable_camera_placement(self):
        self.sample()
        self.tags = self.tags[1:]
        self.arms["green"]["pump_mode"] = "suck"
        self.assertEqual(self.row(self.sample())["stage"], "pickup_suspected")
        self.arms["green"]["pose"] = [350, 250, 80]
        self.assertEqual(self.row(self.sample(advance=.4))["stage"], "likely_carried")
        self.arms["green"]["pump_mode"] = "blow"
        self.assertEqual(self.row(self.sample())["stage"], "release_observed")
        self.tags.append(tag(100, .72, .5))  # raised center maps onto fixed marker 40
        for _ in range(4):
            result = self.sample()
        self.assertEqual(self.row(result)["stage"], "placement_stable")
        self.assertEqual(self.row(result)["target_id"], 40)

    def test_hidden_without_suction_is_unknown_and_reappearance_cancels_carry(self):
        self.sample()
        hidden = self.tags.pop(0)
        self.assertEqual(self.row(self.sample())["stage"], "unknown")
        self.arms["green"]["pump_mode"] = "suck"
        self.assertEqual(self.row(self.sample())["stage"], "pickup_suspected")
        self.tags.append(hidden)
        self.assertNotEqual(self.row(self.sample())["stage"], "likely_carried")
        self.assertFalse(self.tracker.bound)

    def test_stale_frame_invalidates_all_inferences(self):
        self.sample()
        result = self.sample(frame=self.now - 5)
        self.assertEqual(result["status"], "unavailable")
        self.assertTrue(all(t["stage"] == "unknown" for t in result["tags"]))
        self.assertTrue(all(a["considered_tag"] is None for a in result["arms"].values()))
        self.assertFalse(self.tracker.considered)

    def test_camera_dwell_requires_distinct_frames_and_resets_on_occlusion(self):
        self.tags[0] = tag(100, .72, .5)
        first = self.sample()
        for _ in range(4):
            result = self.sample(frame=first["frame_at"])
        self.assertNotEqual(self.row(result)["stage"], "placement_stable")
        self.tags.pop(0)
        self.sample()
        self.tags.append(tag(100, .72, .5))
        self.assertNotEqual(self.row(self.sample())["stage"], "placement_stable")

    def test_missing_projection_has_no_fake_distances_or_arm_overlay(self):
        result = self.sample(projection=False)
        self.assertEqual(result["status"], "ready")  # camera observations still useful
        self.assertEqual(result["arms"]["green"]["candidates"], [])
        self.assertIsNone(result["arms"]["green"]["tcp_camera"])
        self.assertEqual(self.row(result)["stage"], "visible")

    def test_calibration_gap_cannot_rebind_old_occlusion(self):
        self.sample()
        self.tags.pop(0)
        self.sample(projection=False)
        self.arms["green"]["pump_mode"]="suck"
        self.assertEqual(self.row(self.sample())["stage"], "unknown")

    def test_joint_targets_are_not_cartesian_distance(self):
        self.arms["green"]["control_mode"] = "joint"
        result = self.sample()
        self.assertIsNone(result["arms"]["green"]["command_distance"])
        self.assertIn("joint angles", result["arms"]["green"]["command_distance_error"])

    def test_raised_stack_target_is_measured_but_source_is_excluded(self):
        intent={"arms":{"green":{"stage":"target_hover","reported_at":100,"physical_tag":100,"target_marker":101}}}
        output=self.sample(intents=intent)
        targets=output["arms"]["green"]["targets"]
        self.assertEqual(targets[0]["id"],101)
        self.assertEqual(targets[0]["z_mm"],32.5)
        self.assertNotIn(100,[target["id"] for target in targets])

    def test_ambiguous_frame_clears_previous_pickup_candidate(self):
        self.sample()
        self.tags.append(tag(102,.34,.3))
        self.sample()
        self.tags=[tag(40,.7,.5)]
        self.arms["green"]["pump_mode"]="suck"
        self.assertEqual(self.row(self.sample())["stage"],"unknown")

    def test_command_report_never_proves_tag_transport(self):
        intent = {"arms": {"green": {"stage": "operation_completed", "reported_at": 100, "physical_tag": 100}}}
        output = self.sample(intents=intent)
        self.assertEqual(output["arms"]["green"]["controller"]["stage"], "operation_completed")
        self.assertNotEqual(self.row(output)["stage"], "placement_stable")
        self.assertFalse(self.tracker.bound)

    def test_unknown_pump_does_not_confirm_placement(self):
        self.tags[0] = tag(100, .72, .5)
        for a in self.arms.values():
            a["pump_mode"] = "unknown"
        for _ in range(5):
            output = self.sample()
        self.assertNotEqual(self.row(output)["stage"], "placement_stable")

    def test_expired_markers_and_carry_are_forgotten(self):
        self.sample()
        self.tags = []
        output = self.sample(advance=16)
        self.assertEqual(output["tags"], [])


class PhysicalPlacementContractTests(unittest.TestCase):
    def setUp(self):
        self.tracker = PhysicalPlacementTracker()
        self.now = 100.0
        self.tags = [tag(100, .50, .50), tag(40, .52, .50)]
        self.arms = {
            "green": arm([0, 0, 0], self.now),
            "purple": arm([0, 0, 0], self.now),
        }

    def sample(self, advance=0.0, *, status="ready", source="camera"):
        self.now += advance
        for value in self.arms.values():
            value["feedback_at"] = self.now
        runtime = {
            "status": status, "source": source, "frame_at": self.now,
            "tags": copy.deepcopy(self.tags), "arms": copy.deepcopy(self.arms),
        }
        return self.tracker.update(runtime, self.now)

    def test_named_versioned_relationship_requires_unchanged_dwell(self):
        first = self.sample()
        self.assertEqual(first["contract"], "photon.board.placement")
        self.assertEqual(first["version"], 1)
        self.assertFalse(first["relations"][0]["stable"])
        stable = self.sample(.55)
        relation = stable["relations"][0]
        self.assertTrue(relation["stable"])
        self.assertEqual(relation["movable_id"], 100)
        self.assertEqual(relation["marker_id"], 40)
        self.assertEqual(relation["arm"], "green")
        self.assertEqual(stable["coordinate_space"], "corrected-camera-normalized")

    def test_arm_state_and_target_order_reset_stability(self):
        self.sample()
        self.arms["green"]["pump_mode"] = "suck"
        unavailable_for_green = self.sample(.6)
        self.assertFalse(any(row["arm"] == "green" for row in unavailable_for_green["relations"]))
        self.arms["green"]["pump_mode"] = "off"
        resumed = self.sample(.01)
        self.assertFalse(next(row for row in resumed["relations"] if row["arm"] == "green")["stable"])
        self.tags.append(tag(41, .505, .50))
        changed = self.sample(.6)
        green = [row for row in changed["relations"] if row["arm"] == "green"]
        self.assertEqual([row["marker_id"] for row in green], [41, 40])
        self.assertTrue(all(not row["stable"] for row in green))

    def test_stale_or_source_change_clears_authority(self):
        self.sample()
        failed = self.sample(.6, status="unavailable")
        self.assertEqual(failed["status"], "unavailable")
        self.assertEqual(failed["relations"], [])
        resumed = self.sample(.01)
        self.assertFalse(resumed["relations"][0]["stable"])
        previous_epoch = resumed["source_epoch"]
        changed = self.sample(.6, source="simulation")
        self.assertNotEqual(changed["source_epoch"], previous_epoch)
        self.assertFalse(changed["relations"][0]["stable"])


class ProjectionTests(unittest.TestCase):
    def test_forward_reverse_and_height_basis(self):
        projector = CalibrationProjection(calibration())
        data = projector.project([tag(100,.32,.3), tag(40,.7,.5)], {"green": arm([150,150,0])})
        projected = data["arms"]["green"]
        self.assertAlmostEqual(projected["tags"][0]["robot_xy"][0], 150, places=3)
        self.assertAlmostEqual(projected["tcp_camera"][0], .3, places=3)
        self.assertEqual(projected["tags"][0]["drop_z"], 32.5)
        self.assertEqual(projected["tags"][1]["drop_z"], 1)
        self.assertIn("fine tuning", projected["height_basis"])

    def test_missing_parallax_fails_raised_tag_only(self):
        value = calibration()
        value["arms"]["green"]["parallax_points"] = {}
        result = CalibrationProjection(value).project([tag(100,.3,.3), tag(40,.7,.5)], {})
        self.assertEqual(result["arms"]["green"]["tags"][0]["status"], "unavailable")
        self.assertEqual(result["arms"]["green"]["tags"][1]["status"], "ready")

    def test_missing_and_degenerate_six_points_fail_per_side(self):
        value = calibration()
        value["arms"]["green"]["points"] = {}
        result = CalibrationProjection(value).project([], {})
        self.assertEqual(result["arms"]["green"]["status"], "unavailable")
        self.assertEqual(result["arms"]["purple"]["status"], "ready")
        value = calibration()
        for point in value["arms"]["green"]["points"].values():
            point["camera"] = {"u": .1, "v": .1}
        self.assertEqual(CalibrationProjection(value).project([], {})["arms"]["green"]["status"], "unavailable")

    def test_intent_store_filters_late_operation_and_returns_copies(self):
        store = IntentStore()
        store.record("green", "operation_started", {"operation_id":"a", "physical_tag":100}, now=100)
        store.record("green", "operation_started", {"operation_id":"b", "physical_tag":101}, now=101)
        store.record("green", "release_completed", {"operation_id":"a"}, now=102)
        value = store.snapshot()
        self.assertEqual(value["arms"]["green"]["operation_id"], "b")
        value["arms"].clear()
        self.assertTrue(store.snapshot()["arms"])


class HardwareFixture:
    """Public-contract fakes usable by the diagnostic browser smoke test too."""
    def __init__(self):
        self.tags = [tag(100,.30,.30), tag(101,.40,.50), tag(102,.74,.55), tag(103,.62,.4),
                     tag(40,.55,.25), tag(41,.7,.65), tag(42,.25,.7)]
        self.projector = CalibrationProjection(calibration())

    def tag_snapshot(self):
        return {"contract":"hhh.webcam.tags", "version":1, "status":"ready", "observed_at":time.time(),
                "frame_at":time.time(), "width":1600,"height":900,"tags":self.tags,"detections":self.tags,
                "visible_ids":[t["id"] for t in self.tags]}

    def corrected_tag_snapshot(self, tags, detections):
        return {"contract":"hhh.camera-correction", "version":1,"status":"ready","corrected":True,
                "observed_at":time.time(), "width":1600,"height":900,"tags":tags,"detections":detections}

    def arms_snapshot(self):
        return {"contract":"hhh.relay.arms", "version":1,"status":"ready","observed_at":time.time(),
                "arms":{"green":arm([145,155,10],time.time()),"purple":arm([365,280,25],time.time())}}

    def tracking_projection(self,tags,arms):
        return self.projector.project(tags,arms)

    def tracking_intent_snapshot(self):
        return {"contract":"hhh.controller.intent","version":1,"status":"ready","arms":{
            "green":{"stage":"source_hover","reported_at":time.time(),"physical_tag":100,"target_marker":40,"operation_id":"fixture-only"}}}

    def preview_snapshot(self):
        return {"contract":"hhh.camera-preview","version":1,"status":"ready","stream_path":"/api/corrected-stream"}

    def modules(self):
        return {slug:self for slug in ("webcam","camera-calibration","dobot-mg400-relay","auto-pickup-game")}


class BoardIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.board = load("photon-board")
        self.settings_folder = tempfile.TemporaryDirectory()
        self.board.SETTINGS_PATH = self.settings_folder.name + "/tracking-settings.json"
        self.fixture = HardwareFixture()
        self.board.hub_init(FakeContext(self.fixture.modules()))
        self.app = Flask(__name__)
        self.app.register_blueprint(self.board.bp, url_prefix="/p/photon-board")

    def tearDown(self):
        self.board.hub_stop()
        self.settings_folder.cleanup()

    def test_sampler_advances_without_browser_and_readers_return_copies(self):
        first = self.board.tracking_snapshot()
        time.sleep(.25)
        second = self.board.tracking_snapshot()
        self.assertGreater(second["revision"], first["revision"])
        with self.board._sample_lock:
            first = self.board.tracking_snapshot()
            first["tags"].clear()
            self.assertTrue(self.board.tracking_snapshot()["tags"])
            self.assertEqual(self.board.tracking_snapshot()["revision"], first["revision"])
            def unexpected_read():
                raise AssertionError("HTTP readers must not resample hardware")
            original=self.fixture.tag_snapshot
            self.fixture.tag_snapshot=unexpected_read
            try:
                self.assertEqual(self.board.runtime_observation()["status"],"ready")
                self.assertEqual(self.board.board_snapshot()["status"],"ready")
            finally:
                self.fixture.tag_snapshot=original

    def test_existing_contracts_remain_v1_with_additive_tracking(self):
        value = self.board.runtime_observation()
        self.assertEqual(value["status"],"ready")
        self.assertEqual(value["version"],1)
        self.assertEqual(value["tracking"]["contract"],"photon.board.tracking")
        with self.app.test_client() as client:
            with client.get("/p/photon-board/") as page:
                self.assertEqual(page.status_code,200)
            with client.get("/p/photon-board/board-diagnostics.js") as script:
                self.assertEqual(script.status_code,200)
            self.assertEqual(client.get("/p/photon-board/api/diagnostics").status_code,200)
            response=client.get("/p/photon-board/api/preview",environ_overrides={"SCRIPT_NAME":"/s/gamemaster"})
            self.assertEqual(response.headers["Location"],"/s/gamemaster/p/camera-calibration/api/corrected-stream")

    def test_simulation_is_explicit_authenticated_atomic_and_skips_live_intent(self):
        with self.app.test_client() as client:
            payload={"enabled":True,"tags":[tag(100,.32,.3)],"arms":{"green":arm([150,150,0])}}
            self.assertEqual(client.post("/p/photon-board/api/simulation",json=payload).status_code,403)
            response=client.post("/p/photon-board/api/simulation",json=payload,environ_overrides={"hhh.roles":{"gamemaster"}})
            data=response.get_json()["output"]["tracking"]
            self.assertEqual(data["source"],"simulation")
            self.assertIsNone(data["arms"]["green"]["controller"])
            self.assertEqual(client.get("/p/photon-board/api/preview").status_code,409)
            before=copy.deepcopy(self.board._simulation)
            payload["tags"]=[{"id":100,"nx":float("nan"),"ny":0}]
            self.assertEqual(client.post("/p/photon-board/api/simulation",json=payload,environ_overrides={"hhh.roles":{"gamemaster"}}).status_code,400)
            self.assertEqual(self.board._simulation,before)

    def test_disabled_projection_and_stale_feedback_fail_locally(self):
        original=self.fixture.arms_snapshot
        def stale():
            result=original()
            result["arms"]["green"]["feedback_at"]=time.time()-10
            return result
        self.fixture.arms_snapshot=stale
        self.board._sample_tracking()
        self.assertEqual(self.board.tracking_snapshot()["arms"]["green"]["status"],"unavailable")
        self.board.hub_init(FakeContext({k:v for k,v in self.fixture.modules().items() if k!="auto-pickup-game"}))
        output=self.board.tracking_snapshot()
        self.assertEqual(output["inputs"]["cal2_projection"]["status"],"unavailable")
        self.assertTrue(output["tags"])

    def test_malformed_projection_and_changed_contract_clear_inferences(self):
        self.fixture.tracking_projection=lambda *args:{"contract":"hhh.cal2.projection","version":1,"status":"ready","units":"mm","coordinate_space":"wrong","arms":{}}
        self.board._sample_tracking()
        result=self.board.tracking_snapshot()
        self.assertEqual(result["status"],"unavailable")
        self.assertIn("coordinate space", result["errors"][0])
        self.fixture.tracking_projection=lambda *args:{"contract":"hhh.cal2.projection","version":True,"status":"ready"}
        self.board._sample_tracking()
        self.assertEqual(self.board.tracking_snapshot()["inputs"]["cal2_projection"]["status"],"unavailable")

    def test_malformed_coordinate_and_intent_payloads_fail_at_boundary(self):
        projection=self.fixture.tracking_projection
        def malformed(*args):
            value=projection(*args)
            value["arms"]["green"]["tcp_camera"]=["not a number", 0]
            return value
        self.fixture.tracking_projection=malformed
        self.board._sample_tracking()
        self.assertEqual(self.board.tracking_snapshot()["status"],"unavailable")
        self.fixture.tracking_projection=projection
        self.fixture.tracking_intent_snapshot=lambda:{"contract":"hhh.controller.intent","version":1,"status":"ready","arms":{"green":{"stage":42}}}
        self.board._sample_tracking()
        output=self.board.tracking_snapshot()
        self.assertEqual(output["status"],"unavailable")
        self.assertIn("controller stage",output["errors"][0])
        self.assertEqual(self.board.runtime_observation()["status"],"ready") # diagnostics don't break base camera observations

    def test_hub_stop_releases_sampler_and_marks_output_unavailable(self):
        worker=self.board._thread
        self.board.hub_stop()
        self.assertFalse(worker.is_alive())
        self.assertEqual(self.board.tracking_snapshot()["status"],"unavailable")

    def test_browser_renders_only_board_output_and_clears_stale_meters(self):
        node=shutil.which("node")
        if not node:
            self.skipTest("Node required for plain-JS display smoke test")
        snapshot=self.board.tracking_snapshot()
        script=r'''
const fs=require("fs"),vm=require("vm"),assert=require("assert");
const data=JSON.parse(fs.readFileSync(0,"utf8"));
class Element {
  constructor(tag="div"){this.tag=tag;this.children=[];this.style={};this.dataset={};this.attrs={};this.textContent="";this.value="";this.checked=false;this.isConnected=true;}
  append(...nodes){this.children.push(...nodes);}
  replaceChildren(...nodes){this.children=nodes;}
  setAttribute(k,v){this.attrs[k]=v;}
  removeAttribute(k){delete this.attrs[k]; if(k==="src")delete this.src;}
}
const ids="status camera scene feed overlay cameraMessage inputs errors limits arms markers tagRows enabled simulation apply simulationError out settingsForm settingsFields saveSettings defaultSettings settingsStatus settingsError near_xy_mm near_z_mm unique_margin_mm stale_s default_near_xy_mm default_near_z_mm default_unique_margin_mm default_stale_s".split(" ");
const nodes=Object.fromEntries(ids.map(id=>[id,new Element()]));nodes.camera.checked=true;
const all=root=>[root,...root.children.flatMap(all)];
const text=root=>all(root).map(n=>n.textContent).join(" ");
const requests=[],timers=[],sources=[];let clock=10,saveFails=false;
const context={document:{getElementById:id=>nodes[id],createElement:tag=>new Element(tag),createElementNS:(_,tag)=>new Element(tag)},
  location:{pathname:"/s/gamemaster/p/photon-board/"},performance:{now:()=>clock},window:{addEventListener(){}},
  fetch:async(url,options)=>{requests.push([url,options]);if(options?.method==="POST"){
    if(saveFails)return {ok:false,json:async()=>({error:"Save rejected"})};
    return {ok:true,json:async()=>({ok:true,output:{...data.configuration,settings:JSON.parse(options.body).settings}})};
  }return {ok:true,json:async()=>data};},
  EventSource:class {constructor(url){this.url=url;sources.push(this);}close(){}},
  setInterval:fn=>timers.push(fn),console};
vm.runInNewContext(fs.readFileSync(process.argv[1],"utf8"),context);
setImmediate(async()=>{
  assert(text(nodes.arms).includes("Considering tag #100"));
  assert(text(nodes.arms).includes("#100 · CONSIDERED"));
  assert(text(nodes.tagRows).includes("Near arm"));
  assert.equal(all(nodes.arms).filter(n=>n.className?.includes("ltxDistanceSegment")).length,14*24);
  assert.equal(nodes.overlay.attrs.viewBox,"0 0 1000 562.5");
  assert.equal(nodes.scene.style.aspectRatio,"1000/562.5");
  const green=nodes.overlay.children.find(n=>n.tag==="circle");
  assert(Math.abs(Number(green.attrs.cx)-290)<.01);
  assert(Math.abs(Number(green.attrs.cy)-174.375)<.01);
  assert.equal(requests[0][0],"/s/gamemaster/p/photon-board/api/diagnostics");
  assert.equal(sources[0].url,"/s/gamemaster/p/photon-board/api/events");
  assert.equal(Number(nodes.near_xy_mm.value),90);
  assert.equal(Number(nodes.near_z_mm.value),60);
  assert.equal(Number(nodes.unique_margin_mm.value),20);
  assert.equal(Number(nodes.stale_s.value),1.5);
  nodes.near_xy_mm.value="125";nodes.settingsForm.oninput();
  sources[0].onmessage({data:JSON.stringify({tracking:data})});
  assert.equal(nodes.near_xy_mm.value,"125", "SSE must not overwrite a settings draft");
  saveFails=true;await nodes.settingsForm.onsubmit({preventDefault(){}});
  sources[0].onmessage({data:JSON.stringify({tracking:data})});
  assert.equal(nodes.settingsError.textContent,"Save rejected", "SSE must preserve save errors");
  assert.equal(nodes.near_xy_mm.value,"125");
  saveFails=false;await nodes.settingsForm.onsubmit({preventDefault(){}});
  assert.equal(Number(nodes.near_xy_mm.value),125);
  assert.equal(requests.at(-1)[0],"/s/gamemaster/p/photon-board/api/settings");
  assert.equal(JSON.parse(requests.at(-1)[1].body).settings.near_xy_mm,125);
  nodes.defaultSettings.onclick();
  assert.equal(Number(nodes.near_xy_mm.value),90);
  sources[0].onmessage({data:JSON.stringify({tracking:{...data,configuration:{...data.configuration,settings:{...data.configuration.settings,near_xy_mm:125}}}})});
  assert.equal(Number(nodes.near_xy_mm.value),90, "defaults remain an unsaved draft until Apply");
  nodes.simulation.value="unsaved input";nodes.markers.checked=true;
  sources[0].onmessage({data:JSON.stringify({tracking:data})});
  assert.equal(nodes.simulation.value,"unsaved input");
  assert(text(nodes.tagRows).includes("#40"));
  nodes.feed.onerror();
  sources[0].onmessage({data:JSON.stringify({tracking:data})});
  assert.equal(nodes.feed.hidden,true); // A failed preview stays hidden, not a broken img every tick.
  sources[0].onerror();
  assert(!text(nodes.arms).includes("CONSIDERED"));
  assert(text(nodes.tagRows).includes("Unknown"));
  assert(text(nodes.tagRows).includes("Last known / stale"));
  assert(!text(nodes.tagRows).includes("Last seen 0s"));
  nodes.markers.onchange();
  assert(!text(nodes.tagRows).includes("Near arm")); // Toggling cannot revive stale truth.
  sources[0].onmessage({data:JSON.stringify({tracking:data})});
  assert(text(nodes.arms).includes("CONSIDERED"));
  clock=3000;timers[0]();
  assert(!text(nodes.arms).includes("CONSIDERED"));
  assert(nodes.status.textContent.includes("DISCONNECTED"));
  console.log("Board DOM, alignment, meters, stream, draft and stale checks passed");
});
'''
        result=subprocess.run([node,"-e",script,str(PROTOTYPES/"photon-board/board-diagnostics.js")],
                              input=json.dumps(snapshot),text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)


class ProducerIntegrationTests(unittest.TestCase):
    def test_public_projection_and_role_checked_intent_do_not_need_legacy_game(self):
        module=load("auto-pickup-game")
        module._tracking_intents=IntentStore()
        module.hub_init(FakeContext({}))
        app=Flask("tracking-producer")
        app.register_blueprint(module.bp,url_prefix="/auto")
        with app.test_client() as client:
            payload={"team":"purple","kind":"operation_started","detail":{"operation_id":"test-op","physical_tag":100,"target_marker":40}}
            response=client.post("/auto/api/laser-tag-x-intent",json=payload)
            self.assertEqual(response.status_code,403)
            self.assertFalse(module.tracking_intent_snapshot()["arms"])
            response=client.post("/auto/api/laser-tag-x-intent",json=payload,environ_overrides={"hhh.roles":{"green"}})
            self.assertEqual(response.status_code,503) # Existing logging response is preserved.
            value=module.tracking_intent_snapshot()
            self.assertIn("green",value["arms"])
            self.assertNotIn("purple",value["arms"])
            self.assertEqual(value["arms"]["green"]["source"],"controller_report")
            self.assertEqual(module.tracking_projection([],{})["contract"],"hhh.cal2.projection")


if __name__ == "__main__":
    unittest.main()
