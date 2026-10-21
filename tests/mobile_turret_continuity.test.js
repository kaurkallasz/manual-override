/* Read-only projection continuity never certifies an aim command. */
const {test}=require('node:test'),assert=require('node:assert/strict');
const {TurretOverlay}=require('../shared/mobile_ltz/turret-overlay.js');
function fixture(t){
 let now=5000;
 t.mock.method(performance,'now',()=>now);t.mock.method(Date,'now',()=>100000+now-5000);
 const oldDocument=global.document;
 global.document={hidden:false,getElementById:()=>({hasPointerCapture:()=>false})};
 t.after(()=>{global.document=oldDocument;});
 const tower={socket_id:'one',owner:'green',aim_instance:'placed',aim_revision:2};
 const tracking={contract:'photon.board.camera-markers',version:1,status:'ready',source:'camera',
  coordinate_space:'corrected-camera-normalized',camera_identity:'camera-a',camera_revision:'cal-a',width:1280,height:720};
 const camera={status:'ready',matrix:[1,0,0,0,1,0,0,0],frame_at:99.9,width:1280,height:720,tracking};
 const state={run_id:'match',level_revision:1,virtual_play:false,phase:'running',paused:false,server_time:100,
  level:{width:1280,height:720},mobile_camera:camera,towers:[tower]};
 const viewport={w:1280,h:720,vw:844,vh:390,cx:640,cy:360,scale:1,rotation:0,point:(x,y)=>({x,y}),screen:(x,y)=>({x,y})};
 const overlay=Object.assign(Object.create(TurretOverlay.prototype),{
  o:{state:()=>state,fresh:()=>true,viewport},team:'green',selected:'one',epoch:0,drag:null,
  imageAt:4990,image:{hidden:false,width:1280,height:720},registration:null,cameraPacket:null,pendingAim:null,
 });
 const gesture=()=>({key:'placed',revision:2,epoch:overlay.epoch,scope:overlay.gestureScope(),matrix:[...overlay.projection().matrix]});
 const gap=()=>{state.mobile_camera={status:'unavailable',tracking:{...tracking}};};
 return {overlay,state,tracking,tower,viewport,gesture,gap,advance:ms=>{now+=ms;},camera};
}
test('a short marker miss preserves a draft but does not allow a new save or gesture',t=>{
 const f=fixture(t),{overlay}=f,drag=f.gesture();
 assert(overlay.currentGesture(drag));f.gap();f.advance(200);
 assert(overlay.currentGesture(drag));assert(overlay.projection());assert.equal(overlay.ready(),false);
 f.advance(801);assert.equal(overlay.projection(),null);assert.equal(!!overlay.currentGesture(drag),false);
});
test('repeated snapshots of one source frame cannot refresh the display grace',t=>{
 const f=fixture(t),{overlay,state,camera}=f;
 const expires=overlay.projection().expires;
 f.advance(600);state.mobile_camera={...camera};
 assert.equal(overlay.projection().expires,expires);
 f.advance(401);state.mobile_camera={...camera};assert.equal(overlay.projection(),null);
});
test('camera, calibration, level and viewport changes invalidate a gesture immediately',t=>{
 const f=fixture(t),{overlay,state,tracking,viewport}=f;
 for(const mutate of [()=>tracking.camera_identity='camera-b',()=>tracking.camera_revision='cal-b',
  ()=>state.level_revision++,()=>state.run_id='next',()=>viewport.rotation=180]){
  state.mobile_camera={...f.camera,tracking:{...tracking}};
  const drag=f.gesture();mutate();state.mobile_camera={...f.camera,tracking:{...tracking}};
  assert.equal(!!overlay.currentGesture(drag),false);
 }
});
test('tracking loss, tower revision, pause and hidden-page changes cannot submit a retained draft',t=>{
 const f=fixture(t),{overlay,state,tower}=f;
 for(const mutate of [()=>tower.aim_revision++,()=>state.paused=true,()=>document.hidden=true,
  ()=>state.mobile_camera={status:'unavailable'},()=>state.mobile_camera={status:'unavailable',tracking:{...f.tracking,status:'unavailable'}}]){
  state.mobile_camera={...f.camera};state.paused=false;document.hidden=false;
  const drag=f.gesture();mutate();assert.equal(!!overlay.currentGesture(drag),false);
 }
});
test('malformed or stale ready evidence cannot retain the old projection',t=>{
 const f=fixture(t),{overlay,state,camera}=f;
 for(const changed of [{matrix:[1,0]},{matrix:[NaN,0,0,0,1,0,0,0]},{frame_at:95}]){
  state.mobile_camera={...camera};assert(overlay.projection());
  state.mobile_camera={...camera,...changed};assert.equal(overlay.projection(),null);
 }
});
test('small registration jitter does not change the active pointer mapping; a real shift cancels it',t=>{
 const f=fixture(t),{overlay,state,camera}=f;
 overlay.drag=f.gesture();overlay.draft={angle:30,spread:.4};
 const before=overlay.world({x:300,y:200});
 state.mobile_camera={...camera,matrix:[1,0,.001,0,1,.001,0,0],frame_at:99.95};
 assert(overlay.currentGesture(overlay.drag));assert.deepEqual(overlay.world({x:300,y:200}),before);
 state.mobile_camera={...camera,matrix:[1,0,.1,0,1,0,0,0],frame_at:100};
 const drag=overlay.drag;assert.equal(!!overlay.currentGesture(drag),false);
 assert.equal(overlay.drag,null);assert.equal(overlay.draft,null);
});
test('home defenses use the same ownership and destruction checks; previews cannot be selected',t=>{
 const {overlay,state,tower}=fixture(t);
 const starter={...tower,socket_id:'starter_green_1',is_starter:true};
 state.starter_turrets=[starter];overlay.selected=starter.socket_id;
 assert.equal(overlay.tower(),starter);
 starter.preview=true;assert.equal(overlay.tower(),undefined);
 starter.preview=false;starter.owner='purple';assert.equal(overlay.tower(),undefined);
 starter.owner='green';starter.destroyed=true;assert.equal(overlay.tower(),undefined);
 assert.equal(state.towers.length,1);
});
