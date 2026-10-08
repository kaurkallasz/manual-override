/* Real mobile height handlers, with no browser or hardware connection. */
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('shared/mobile_ltz/mobile.js','utf8');
function context(status){
 const nodes=new Map();
 const c={controlMode:'cue',cueBusy:false,switchBusy:false,ready:true,xyzTarget:{x:900,y:800,z:60},xyzEdit:0,
  xyzError:'',pendingXYZ:false,pendingXYZTarget:null,xyzCenters:{z:0},xyzPointer:null,
  controlPointers:new Set(),mapPointers:new Map(),document:{hidden:false},zPresets:[75,null,999],
  state:{virtual_play:false,mobile_arm:{enabled:true,tip:{x:300,y:200,z:50},xyz_limits:{z:[-102,80]},cue:{status}}},
  cartesian:()=>true,feedback(){},updateXYZ(){},xyzDirection:()=>1,
  $:id=>{if(!nodes.has(id))nodes.set(id,{handlers:{},addEventListener(name,fn){this.handlers[name]=fn;},setPointerCapture(){}});return nodes.get(id);}};
 c.available=()=>c.ready;c.cueLocked=()=>['running','paused','waiting'].includes(c.state.mobile_arm.cue.status);
 vm.createContext(c);
 for(const [a,b] of [
  ['function manualAvailable()', 'function cueCandidates()'],
  ['function canUseZPresets()', 'function cancelZPresetHold()'],
  ['function recallZPreset(', 'function startZPresetHold('],
  ["for(const axis of ['x','y','z']){\n const el=$('xyz'", 'const xyzStepButtons=']
 ])vm.runInContext(source.slice(source.indexOf(a),source.indexOf(b)),c);
 return c;
}
test('slider and preset recall override running/paused cues and work while idle',()=>{
 for(const status of ['idle','running','paused','waiting','stopped','completed','error']){
  const c=context(status);assert(c.canUseZPresets(),status);
  c.$('xyzZ').value=65;c.$('xyzZ').handlers.input();
  assert(c.pendingXYZ);assert.deepEqual({...c.pendingXYZTarget},{x:300,y:200,z:65});
  c.pendingXYZ=false;c.recallZPreset(0);assert(c.pendingXYZ);
  assert.deepEqual({...c.pendingXYZTarget},{x:300,y:200,z:75});
  assert.equal(c.state.mobile_arm.cue.status,status);
  if(['running','paused','waiting'].includes(status))assert(!c.manualAvailable(),'Joint/pump/manual XY remain owned by the cue');
 }
});
test('height input still requires readiness and valid preset limits',()=>{
 for(const block of ['unavailable','disabled','busy','switching']){
  const c=context('running');
  if(block==='unavailable')c.ready=false;if(block==='disabled')c.state.mobile_arm.enabled=false;
  if(block==='busy')c.cueBusy=true;if(block==='switching')c.switchBusy=true;
  c.$('xyzZ').value=65;c.$('xyzZ').handlers.input();c.recallZPreset(0);assert(!c.pendingXYZ,block);
 }
 const c=context('running');c.recallZPreset(1);c.recallZPreset(2);assert(!c.pendingXYZ);
 c.$('xyzX').value=45;c.$('xyzX').handlers.input();assert(!c.pendingXYZ,'Cue cannot send XY from a slider');
});
