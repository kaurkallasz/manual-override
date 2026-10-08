/* Real mobile renderer with camera/arm snapshots; no robot or network I/O. */
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('shared/mobile_ltz/mobile.js','utf8');
function renderer(){
 const nodes=new Map();
 const c={cuePickupPreview:null,controlMode:'cue',xyzTarget:{x:300,y:200,z:80},feedReady:true,lastFeed:0,
  performance:{now:()=>100},cartesian:()=>true,
  viewport:{w:1696,h:960,vw:844,vh:390,scale:.5,point:(x,y)=>({x,y})},
  state:{run_id:'game-1',mobile_arm:{session:'arm-1',control_revision:4,tip:{x:300,y:200,z:80},
   tags:[{id:100,x:400,y:300},{id:101,x:450,y:350}],markers:[{id:42,x:800,y:600}],
   cue:{rows:[{piece:100,destination:42},{action:'clear_view'},{piece:101,destination:42}],index:0,status:'idle'}}},
  $:id=>{if(!nodes.has(id))nodes.set(id,{dataset:{},attrs:{},setAttribute(k,v){this.attrs[k]=v;},toggleAttribute(k,on){if(on)this.attrs[k]='';else delete this.attrs[k];}});return nodes.get(id);}};
 c.displayedArmTip=()=>c.state?.mobile_arm?.tip;c.drawArmTrajectory=()=>{};
 vm.createContext(c);vm.runInContext(source.slice(source.indexOf('function drawXYZ(){'),source.indexOf('function updateXYZMarkers(')),c);
 c.visible=()=>!Object.hasOwn(c.$('cuePickupBullseye').attrs,'hidden');
 c.position=id=>c.$(id||'cuePickupBullseye').attrs.transform;
 return c;
}
test('Play marks the source in a separate bullseye and preserves the final destination',()=>{
 const c=renderer();c.drawXYZ();assert(!c.visible());
 c.state.mobile_arm.cue.status='running';c.drawXYZ();assert(c.visible());
 assert.equal(c.position(),'translate(400 300) scale(2)');
 assert.equal(c.$('cuePickupBullseye').attrs['aria-label'],'Cyan pickup 100 X 400.0, Y 300.0');
 assert.equal(c.position('xyzTargetBullseye'),'translate(800 600) scale(2)');
 assert.equal(c.position('xyzActualBullseye'),'translate(300 200) scale(2)');
});
test('pickup stays anchored through occlusion, pause, camera wait and zoom',()=>{
 const c=renderer(),a=c.state.mobile_arm;a.cue.status='running';c.drawXYZ();
 a.tags=[];a.cue.status='waiting';c.drawXYZ();assert(c.visible());
 a.tags=[{id:100,x:700,y:500}];a.tip={x:700,y:500,z:80};a.cue.status='paused';c.drawXYZ();
 assert.equal(c.position(),'translate(400 300) scale(2)');
 c.viewport.scale=1;c.drawXYZ();assert.equal(c.position(),'translate(400 300) scale(1)');
 assert.equal(c.position('xyzTargetBullseye'),'translate(800 600) scale(1)');
});
test('confirmed pickup hides cyan immediately and release cannot make it reappear',()=>{
 for(const physical of [false,true]){
  const c=renderer(),a=c.state.mobile_arm;a.cue.status='running';c.drawXYZ();assert(c.visible());
  if(physical)a.cue.picked_up=true;else a.held_tag=100;
  c.drawXYZ();assert(!c.visible());assert.equal(c.position('xyzTargetBullseye'),'translate(800 600) scale(2)');
  a.cue.status='paused';a.cue.picked_up=false;a.held_tag=null;a.tags[0]={id:100,x:800,y:600};c.drawXYZ();assert(!c.visible());
  a.cue.status='completed';c.drawXYZ();a.cue.status='running';c.drawXYZ();assert(c.visible());
  assert.equal(c.position(),'translate(800 600) scale(2)');
 }
});
test('clearance and completion remove the pickup; later rows and replay use fresh positions',()=>{
 const c=renderer(),a=c.state.mobile_arm;a.cue.status='running';c.drawXYZ();
 a.cue.index=1;c.drawXYZ();assert(!c.visible());
 a.cue.index=2;c.drawXYZ();assert.equal(c.position(),'translate(450 350) scale(2)');
 a.cue.status='completed';c.drawXYZ();assert(!c.visible());
 a.tags[0]={id:100,x:800,y:600};a.cue.index=0;a.cue.status='running';c.drawXYZ();
 assert.equal(c.position(),'translate(800 600) scale(2)');
 a.cue.status='stopped';c.drawXYZ();assert(!c.visible());
});
test('missing source waits for a valid sighting and never carries a preview into another game/session/mode',()=>{
 const c=renderer(),a=c.state.mobile_arm;a.cue.status='running';a.tags=[];c.drawXYZ();assert(!c.visible());
 a.tags=[{id:100,x:NaN,y:200}];c.drawXYZ();assert(!c.visible());
 a.tags=[{id:100,x:400,y:300}];c.drawXYZ();assert(c.visible());
 a.session='arm-2';a.tags=[];c.drawXYZ();assert(!c.visible());
 a.tags=[{id:100,x:600,y:500}];c.drawXYZ();assert(c.visible());
 c.state.run_id='game-2';a.tags=[];c.drawXYZ();assert(!c.visible());
 a.tags=[{id:100,x:400,y:300}];c.drawXYZ();c.controlMode='xyz';c.drawXYZ();assert(!c.visible());
});
