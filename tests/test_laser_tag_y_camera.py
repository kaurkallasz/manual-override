"""Operator camera state smoke test, without camera hardware or robot commands."""
import shutil
import subprocess
import unittest
from pathlib import Path


@unittest.skipUnless(shutil.which("node"), "Node.js required")
class OperatorCameraTests(unittest.TestCase):
    def test_modes_failures_recovery_and_disconnect(self):
        root = Path(__file__).resolve().parents[1]
        page = (root / "sandboxes/gamemaster/prototypes/laser-tag-y/index.html").read_text()
        source = page.split("function createOperatorCamera", 1)[1].split("// This monitor", 1)[0]
        script = r'''
const assert=require('node:assert/strict');
let now=0;const performance={now:()=>now};
const stage={classList:{toggle(name,on){this[name]=on}}};
const image={hidden:true,src:null,removeAttribute(){this.src=null}};
const message={},retry={},fps={};let retries=0;
const camera=createOperatorCamera({stage,image,message,retry,fps,onRetry:()=>retries++});
const frame=(patch={})=>({contract:'laser-tag-y.camera',version:1,status:'ready',frame_at:Date.now()/1000,width:3840,height:2160,image:'data:image/jpeg;base64,ZmFrZQ==',...patch});
const show=()=>{camera.frame(frame());image.onload()};
const state={status:'ready',virtual_play:false,inputs:{board:{status:'ready',upstream:{source:'camera'}}}};
camera.update(state);
assert.equal(stage.classList.rendered,false);
assert.equal(image.src,null,'Game updates never open a second MJPEG connection');
image.onload();assert.equal(image.hidden,true,'A late load without a fresh frame cannot expose old pixels');
show();assert.equal(image.hidden,false);assert.match(message.textContent,/Live camera/);
camera.update(state);assert.equal(image.hidden,false);
image.onerror();assert.equal(image.hidden,true);assert.equal(retry.hidden,false);
show();assert.equal(image.hidden,false,'The next good frame recovers without manual intervention');
for(const patch of [{contract:'wrong'},{version:true},{status:'unavailable',error:'Camera disconnected'},{frame_at:Date.now()/1000-3},{frame_at:Date.now()/1000+2},{width:0},{image:'/untrusted.jpg'}]){
 camera.frame(frame(patch));image.onload();assert.equal(image.hidden,true);assert.equal(image.src,null);
 show();assert.equal(image.hidden,false);
}
now=2600;camera.update(state);camera.check();assert.equal(image.src,null,'Fresh game state cannot keep an expired image alive');
show();assert.equal(image.hidden,false);
camera.update({...state,virtual_play:true});show();assert.equal(stage.classList.rendered,true);assert.equal(image.src,null);assert.equal(fps.hidden,false);
camera.update({...state,inputs:{board:{status:'ready',upstream:{source:'simulation'}}}});
show();assert.equal(stage.classList.rendered,true);assert.equal(image.src,null);
camera.update(state);show();camera.disconnect();show();assert.equal(image.hidden,true);assert.equal(image.src,null);
camera.update(state);show();now+=3100;camera.check();assert.equal(image.src,null);
camera.update(state);show();assert.equal(image.hidden,false);
camera.update({...state,inputs:{board:{status:'unavailable',error:'frame stale',upstream:{source:'camera'}}}});
show();assert.equal(stage.classList.rendered,false);assert.equal(image.src,null);assert.match(message.textContent,/frame stale/);
const calibration={...state,journey:{phase:'calibration',active_side:'purple'},inputs:{board:{status:'unavailable',error:'game markers replaced',upstream:{source:'camera'}}}};
camera.update(calibration);assert.equal(stage.classList['calibration-camera'],true);show();assert.equal(image.hidden,false);
camera.suspend();camera.update(calibration);camera.check();show();
assert.equal(image.src,null,'Neither events nor the watchdog can reopen a suspended camera');
assert.equal(image.hidden,true);
camera.resume();assert.equal(image.src,null);show();assert.equal(image.hidden,false);
image.onerror();assert.equal(image.hidden,true);assert.equal(retry.hidden,false);
retry.onclick();assert.equal(retries,1);assert.equal(image.src,null);show();assert.equal(image.hidden,false);
camera.update({...calibration,journey:{phase:'lobby'}});assert.equal(image.src,null);assert.equal(stage.classList['calibration-camera'],false);
camera.update(state);now+=3100;camera.update(state);camera.check();
assert.match(message.textContent,/frames delayed/);assert.equal(retry.hidden,false);
camera.destroy();assert.equal(image.src,null);
'''
        result = subprocess.run([shutil.which("node"), "-e", "function createOperatorCamera" + source + script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        # Both inline scripts must parse, and the external screen stays rendered.
        for block in page.split("<script>")[1:]:
            result = subprocess.run([shutil.which("node"), "--check"], input=block.split("</script>")[0], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        screen = (root / "sandboxes/gamemaster/prototypes/laser-tag-y/screen.html").read_text()
        self.assertNotIn('id="boardCamera"', screen)
        self.assertNotIn('CalibrationDisplay.create', page)
        self.assertIn('CalibrationDisplay.create', screen)

    def test_aruco_overlay_visibility_cache_expiry_and_stream_lifecycle(self):
        root = Path(__file__).resolve().parents[1]
        page = (root / "sandboxes/gamemaster/prototypes/laser-tag-y/index.html").read_text()
        source = "function createArucoMonitor" + page.split("function createArucoMonitor", 1)[1].split("const arucoMonitor=", 1)[0]
        chip_source = "function detectionChip" + page.split("function detectionChip", 1)[1].split("function renderControls", 1)[0]
        script = r"""
const assert=require('node:assert/strict');
let time=100,result;
function node(){return {attrs:{},children:[],textContent:'',setAttribute(k,v){this.attrs[k]=v},toggleAttribute(k,v){if(v)this.attrs[k]='';else delete this.attrs[k]},hasAttribute(k){return k in this.attrs},append(c){this.children.push(c)},replaceChildren(){this.children=[]}}}
const document={createElementNS:node,createElement:node},overlay=node();
const monitor=createArucoMonitor({overlay,now:()=>time,onChange:value=>result=value});
const tag=(id,visible=true,last_seen=time)=>({id,kind:id>=100?'movable':'marker',visible,last_seen,camera:[.5,.5],corners:[[.4,.4],[.6,.4],[.6,.6],[.4,.6]]});
const payload=(tags=[tag(40)],patch={})=>({contract:'photon.board',version:1,tracking:{contract:'photon.board.tracking',version:1,status:'ready',source:'camera',sampled_at:time,frame_at:time,width:1920,height:1080,coordinate_space:'corrected-camera-normalized',limits:{stale_s:1.5},tags,...patch,camera_markers:{contract:'photon.board.camera-markers',version:1,status:'ready',source:'camera',coordinate_space:'corrected-camera-normalized',width:1920,height:1080,frame_at:time,max_age_s:1.5,tags:tags.filter(t=>t.visible&&Number.isSafeInteger(t.id)&&Array.isArray(t.camera)&&t.camera.every(Number.isFinite)),...patch}}});
const send=(value=payload())=>monitor.update(value.tracking);
// The first shared-stream diagnostic may arrive before the camera image loads.
send();assert.equal(result.ready,false);monitor.setEnabled(true);assert.equal(result.ready,true);
monitor.disconnect();assert.equal(overlay.hasAttribute('hidden'),true);
send(payload([tag(40),tag(41,false,98),tag(42,false,94),tag(100,false,90),tag(101,false,84)]));
assert.equal(result.ready,true);assert.deepEqual(result.tags.map(t=>t.id),[40,41,100]);
assert.equal(overlay.attrs.viewBox,'0 0 1920 1080');
assert.equal(overlay.children[0].attrs.points,'768,432 1152,432 1152,648 768,648');
assert.equal(overlay.children[0].attrs['stroke-dasharray'],'none');
assert.equal(overlay.children[2].attrs['stroke-dasharray'],'5 4');
assert.match(overlay.children[3].textContent,/#41.*2.0s ago/);
// Physical disabled chips remain status indicators, while virtual chips have no detection state.
const ui={aruco:result};
function button(){const b=node();b.classList={add(name){b[name]=true}};return b}
let b=button();detectionChip(b,40,false);assert.equal(b.detected,true);assert.equal(b.children[0].textContent,'✓ Found');
b=button();detectionChip(b,41,false);assert.equal(b.remembered,true);assert.match(b.children[0].textContent,/Seen 2s ago/);
b=button();detectionChip(b,55,false);assert.equal(b.children[0].textContent,'Not seen');
b=button();detectionChip(b,40,true);assert.equal(b.children.length,0);
monitor.setEnabled(true);assert.equal(result.ready,true);
// Retained coordinates cannot remain green after a lost or stale stream.
monitor.disconnect();assert.equal(result.ready,false);assert.equal(result.tags.length,0);assert.equal(overlay.hasAttribute('hidden'),true);
send();assert.equal(result.tags[0].visible,true);time+=1.6;monitor.check();assert.equal(result.ready,false);assert.equal(overlay.children.length,0);
send(payload([tag(40)],{frame_at:time-2}));assert.equal(result.ready,false);
// Diagnostic inference freshness cannot override the shared camera evidence.
send(payload([tag(40)],{sampled_at:time-2}));assert.equal(result.ready,true);
send(payload([tag(40)],{frame_at:time+1}));assert.equal(result.ready,false);
send(payload([tag(40)],{source:'simulation'}));assert.equal(result.ready,false);
send(payload([tag(40)],{coordinate_space:'raw'}));assert.equal(result.ready,false);
send(payload([tag(40)],{status:'unavailable'}));assert.equal(result.ready,false);
send(payload([],{contract:'wrong'}));assert.equal(result.ready,false);assert.match(result.error,/Incompatible/);
send(payload([],{version:2}));assert.equal(result.ready,false);
monitor.update(null);assert.equal(result.ready,false);
send(payload([{...tag(40),camera:['.5',.5]}, {...tag(41),id:'41'}, {...tag(42),corners:[[2,2]]}]));
assert.deepEqual(result.tags.map(t=>t.id),[40,42]);assert.equal(result.tags[0].cached,true);assert.equal(overlay.children[2].attrs.width,'38.4');
monitor.setEnabled(false);assert.equal(result.ready,false);
send();assert.equal(result.ready,false);
monitor.setEnabled(true);assert.equal(result.ready,true);
monitor.destroy();assert.equal(overlay.hasAttribute('hidden'),true);
"""
        result = subprocess.run([shutil.which("node"), "-e", source + chip_source + script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('transform:scale(1.15)', page)
        self.assertIn("virtual?'Virtual Atom controls':'Aruco MNGMNT'", page)

    def test_table_cache_persists_resets_and_never_becomes_live_evidence(self):
        root = Path(__file__).resolve().parents[1]
        page = (root / "sandboxes/gamemaster/prototypes/laser-tag-y/index.html").read_text()
        source = "function createArucoMonitor" + page.split("function createArucoMonitor", 1)[1].split("const arucoMonitor=", 1)[0]
        script = r"""
const assert=require('node:assert/strict');
let time=100,saved=null,result,writes=0,calibration=false;
const document={createElementNS(){return {setAttribute(){}}}};
const overlay={nodes:[],setAttribute(){},toggleAttribute(){},replaceChildren(){this.nodes=[]},append(n){this.nodes.push(n)}};
const options={overlay,isCalibration:()=>calibration,now:()=>time,onChange:r=>result=r,readCache:()=>saved,writeCache:v=>{saved=structuredClone(v);writes++}};
const tag=id=>({id,kind:id>=100?'movable':'marker',visible:true,last_seen:time,camera:[.2,.3],corners:[]});
function send(tags=[],patch={}){monitor.update({contract:'photon.board.tracking',version:1,status:'ready',source:'camera',coordinate_space:'corrected-camera-normalized',width:1920,height:1080,sampled_at:time,frame_at:time,tags,...patch,camera_markers:{contract:'photon.board.camera-markers',version:1,status:'ready',source:'camera',coordinate_space:'corrected-camera-normalized',width:1920,height:1080,frame_at:time,max_age_s:1.5,tags,...patch}})}
let monitor=createArucoMonitor(options);monitor.setEnabled(true);send([tag(38),tag(40),tag(59),tag(60),tag(100)]);
assert.equal(result.cachedCount,2);assert.deepEqual(saved.tags.map(t=>t.id),[40,59]);
// Locations survive Board's five-second history and gameplay's 120-second cache.
time+=200;send();assert.deepEqual(result.tags.map(t=>[t.id,t.cached,t.visible]),[[40,true,false],[59,true,false]]);
assert.equal(result.tags[0].age,200);
assert(overlay.nodes.some(n=>n.textContent?.includes('40')));
calibration=true;monitor.check();assert.equal(overlay.nodes.length,0);assert.equal(result.cachedCount,2);
send([tag(31)]);assert(overlay.nodes.some(n=>n.textContent?.includes('31')));assert(!overlay.nodes.some(n=>n.textContent?.includes('cached')));
calibration=false;monitor.check();assert(overlay.nodes.some(n=>n.textContent?.includes('40')));monitor.destroy();
// Browser reload restores only validated table entries. It cannot light a chip as currently visible.
monitor=createArucoMonitor(options);monitor.setEnabled(true);assert.equal(result.ready,false);send();assert.equal(result.tags[0].cached,true);
// Lost evidence hides cached geometry without erasing it. Recovery uses fresh frames.
monitor.disconnect();assert.equal(result.tags.length,0);assert.equal(result.cachedCount,2);time+=1;send();assert.equal(result.tags.length,2);
// A reset removes saved and in-memory locations, including still-visible data from the old frame.
send([tag(40)]);monitor.resetCache();assert.equal(saved,null);assert.equal(result.cachedCount,0);assert.equal(result.tags.length,0);
monitor.check();assert.equal(result.cachedCount,0);time+=.2;send([tag(40)]);assert.equal(result.cachedCount,1);assert.equal(result.tags[0].visible,true);
// Cache writes are throttled but teardown flushes the latest detected position.
const before=writes;time+=.2;send([{...tag(40),camera:[.8,.7]}]);assert.equal(writes,before);monitor.destroy();assert.deepEqual(saved.tags[0].camera,[.8,.7]);
// Frame-size changes invalidate old geometry rather than displaying it in another coordinate frame.
monitor=createArucoMonitor(options);monitor.setEnabled(true);send([],{width:1280,height:720});assert.equal(result.cachedCount,0);assert.equal(result.tags.length,0);monitor.destroy();
// Malformed saved input cannot seed an overlay; storage failure leaves an explicit visit-only cache.
saved={version:1,width:1920,height:1080,tags:[{id:100,camera:[.5,.5],last_seen:100,corners:null}]};
monitor=createArucoMonitor({...options,writeCache(){throw Error('storage blocked')}});monitor.setEnabled(true);assert.equal(result.cachedCount,0);send([tag(45)]);assert.match(result.cacheError,/visit only.*storage blocked/);assert.equal(result.cachedCount,1);
monitor.resetCache();assert.equal(result.cachedCount,0);assert.match(result.cacheError,/storage blocked/);monitor.destroy();
// A false outline saved by the old client must not survive the new size rule.
const sized=(id,size)=>({...tag(id),corners:[[-1,-1],[1,-1],[1,1],[-1,1]].map(([x,y])=>[.2+x*size/3840,.3+y*size/2160])});
saved={version:1,width:1920,height:1080,tags:[sized(40,40),sized(49,200)]};
monitor=createArucoMonitor(options);monitor.setEnabled(true);
const size_filter={status:'ready',max_ratio:1.15,minimum_px:40,maximum_px:40,rejected:[]};
send([sized(40,40),sized(41,40)],{size_filter});
assert.deepEqual(result.tags.map(t=>t.id),[40,41]);assert(!saved.tags.some(t=>t.id===49),'Oversized cached 49 is purged even when not visible now');
time+=2;send([sized(40,40)],{size_filter:{...size_filter,rejected:[{id:41,size_px:200,reason:'size_outlier'}]}});
assert.deepEqual(result.tags.map(t=>t.id),[40]);assert(!saved.tags.some(t=>t.id===41),'Explicit size rejection cannot fall back to cached geometry');
monitor.destroy();

"""
        result = subprocess.run([shutil.which("node"), "-e", source + script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
