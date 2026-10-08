const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const {PositionPlayback}=require('../shared/mobile_ltz/joint-rig.js');
const source=fs.readFileSync('shared/mobile_ltz/mobile.js','utf8');
test('faster mobile feedback reuses the controller poll and never overlaps requests',async()=>{
 const source=fs.readFileSync('shared/robot_controls/controller.html','utf8');
 for(const [mobile,search,expected] of [[true,'?bridge=1',100],[true,'',500],[false,'?bridge=1',500]]){
  let calls=0,release,fail=false,applied=0;
  const c={MOBILE_LTZ:mobile,URLSearchParams,location:{search},armConnectBusy:false,armPollBusy:false,
   api:async()=>{calls++;await new Promise(resolve=>release=resolve);if(fail)throw Error('timeout');return {};},
   applyStatus:()=>applied++,guardCal2BaseApproach:async()=>{}};
  vm.createContext(c);vm.runInContext(source.match(/^const ARM_STATUS_POLL_MS = .+;$/m)[0],c);
  assert.equal(vm.runInContext('ARM_STATUS_POLL_MS',c),expected);
  vm.runInContext(source.slice(source.indexOf('async function poll() {'),source.indexOf('function applyStatus(s) {')),c);
  const first=c.poll();await c.poll();await c.poll();assert.equal(calls,1,'A slow status read cannot queue overlapping requests');
  release();await first;assert.equal(applied,1);
  fail=true;const failed=c.poll();release();await assert.rejects(failed,/timeout/);assert.equal(c.armPollBusy,false);
  c.armConnectBusy=true;await c.poll();assert.equal(calls,2,'Connection synchronization still owns the link');
 }
});
function display(){
 const nodes=new Map(),c={now:1000,feedReady:true,lastFeed:1000,xyzMotionScope:null,xyzPathProgress:null,
  xyzMotion:new PositionPlayback(),
  performance:{now:()=>c.now},document:{hidden:false},controlMode:'cue',cuePickupPreview:null,
  xyzTarget:{x:200,y:100,z:60},cartesian:()=>true,xyzDirection:()=>1,xyzSliderBounds:()=>[0,1000],
  viewport:{w:1000,h:600,vw:1000,vh:600,scale:1,point:(x,y)=>({x,y})},
  state:{run_id:'run',virtual_play:true,mobile_arm:{position_at:1,session:'arm',control_revision:1,tip:{x:0,y:0,z:60},tags:[],markers:[],cue:{status:'idle'}}},
  $:id=>{if(!nodes.has(id))nodes.set(id,{dataset:{},style:{},attrs:{},setAttribute(k,v){this.attrs[k]=v;},toggleAttribute(k,v){if(v)this.attrs[k]='';else delete this.attrs[k];}});return nodes.get(id);}};
 vm.createContext(c);vm.runInContext(source.slice(source.indexOf('function displayedArmTip(){'),source.indexOf("for(const axis of ['x','y','z']){\n const el=")),c);
 c.frame=()=>{c.now+=1000/30;c.lastFeed=c.now;c.updateXYZMarkers(1/30);};
 c.route=points=>{c.state.mobile_arm.motion_path={id:'path-1',points:points.map(([x,y])=>({x,y,z:60}))};};
 return c;
}
test('5 Hz feedback produces steady 30 fps movement, without easing at packet boundaries',()=>{
 const c=display();c.drawXYZ();let previous=0,changes=0;
 for(let i=1;i<=60;i++){
  if(i%6===0){c.state.mobile_arm.tip.x=i/6*20;c.state.mobile_arm.position_at=(c.now+1000/30)/1000;}
  const actual=c.state.mobile_arm.tip.x;c.frame();const shown=c.displayedArmTip().x;
  assert(shown>=previous&&shown<=actual);if(shown>previous+.01)changes++;previous=shown;
  if(i>=8)assert(Math.abs(shown-(i*1000/30-250)*.1)<1e-8,'Speed must remain 100 units/sec through every packet');
  assert.equal(c.state.mobile_arm.tip.x,actual);
  assert.equal(c.$('xyzTargetBullseye').attrs.transform,'translate(200 100) scale(1)');
 }
 assert(changes>=52);assert(previous>170);
 assert.match(c.$('xyzActualGuides').attrs.d,new RegExp('M'+previous+' '));
});
test('physical 100 ms samples with delivery jitter stay steady with only 150 ms of playback delay',()=>{
 const c=display();c.state.virtual_play=false;c.drawXYZ();
 const samples=Array.from({length:61},(_,i)=>({at:i*100,receipt:i*100+[0,20,5,25,10,15][i%6]}));
 let index=0,previous=0;const speeds=[];
 for(let elapsed=1000/30;elapsed<=6000;elapsed+=1000/30){
  c.now=1000+elapsed;c.lastFeed=c.now;
  while(samples[index+1]?.receipt<=elapsed){index++;c.state.mobile_arm.position_at=1+samples[index].at/1000;c.state.mobile_arm.tip={x:samples[index].at*.1,y:0,z:60};}
  c.updateXYZMarkers(1/30);const shown=c.displayedArmTip().x;
  if(elapsed>1000)speeds.push((shown-previous)*30);previous=shown;
  assert(shown<=c.state.mobile_arm.tip.x,'No prediction beyond received feedback');
  if(elapsed>1000)assert(Math.abs(shown-(elapsed-150)*.1)<1e-8,'No accumulated display lag');
 }
 assert(Math.max(...speeds)-Math.min(...speeds)<1e-8,'No recurring deceleration/acceleration');
 assert(Math.abs(speeds[0]-100)<1e-8);
});
test('a measured stop flushes the display to the actual endpoint and stays there',()=>{
 const c=display();c.state.virtual_play=false;c.drawXYZ();c.route([[0,0],[200,0]]);
 for(let i=1;i<=15;i++){c.state.mobile_arm.tip.x=i*10;c.state.mobile_arm.position_at=1+i*.1;c.now=1000+i*100;c.lastFeed=c.now;c.updateXYZMarkers(.1);}
 assert(c.displayedArmTip().x<150);c.state.mobile_arm.position_settled=true;c.state.mobile_arm.position_at=2.6;c.now=2600;c.lastFeed=c.now;c.updateXYZMarkers(.1);
 assert.equal(c.displayedArmTip().x,150,'Stop at the measured pose, not the unfinished 200 target');
 assert.equal(c.$('xyzArmTrajectory').attrs.d,'M150.00 0.00L200.00 0.00');
 for(let i=0;i<15;i++)c.frame();assert.equal(c.displayedArmTip().x,150,'No motion after the actual stop');
 c.state.mobile_arm.position_settled=false;c.state.mobile_arm.position_at=3.2;c.state.mobile_arm.tip.x=160;c.frame();assert(c.displayedArmTip().x<=160);
 c.state.mobile_arm.position_at=3.3;c.state.mobile_arm.tip.x=200;c.state.mobile_arm.position_settled=true;c.frame();
 assert.equal(c.displayedArmTip().x,200);assert('hidden' in c.$('xyzArmTrajectory').attrs);
});
test('measured stops, reversals, late packets and underruns never overshoot or catch up in a jump',()=>{
 const m=new PositionPlayback(),p=x=>({x,y:0,z:60});
 m.update(p(0),0,0,250);m.update(p(20),200,200,250);
 assert.equal(m.update(p(20),400,400,250).x,15);
 assert.equal(m.update(p(10),600,600,250).x,20,'Actual stationary samples keep the stop');
 assert.equal(m.update(p(10),600,750,250).x,15,'Reverse only after measured reversal');
 assert.equal(m.update(p(999),100,800,250,true).x,12.5,'Ignore out-of-order feedback, including an obsolete stop');
 assert.equal(m.update(p(10),600,1000,250).x,10,'Hold when there is no newer measurement');
 assert.equal(m.update(p(30),1000,1000,250).x,10,'New packet cannot cause a catch-up jump');
 assert.equal(m.update(p(30),1000,1100,250).x,15);
 assert.equal(m.update(p(30),1000,2000,250).x,30);
 assert.equal(m.update(p(50),4000,4000,250).x,50,'Long interruption resets');
 assert.equal(m.update({x:NaN,y:0,z:60},4100,4100),null);
 assert.equal(m.update(p(60),undefined,4200).x,60,'Legacy missing timestamp stays raw');
});
test('remaining dashed route erases passed portions and does not regrow on jitter',()=>{
 const c=display();c.route([[0,0],[100,0],[100,100]]);c.drawXYZ();
 assert.equal(c.$('xyzArmTrajectory').attrs.d,'M0.00 0.00L100.00 0.00L100.00 100.00');
 c.drawArmTrajectory({x:60,y:0},true);assert.equal(c.$('xyzArmTrajectory').attrs.d,'M60.00 0.00L100.00 0.00L100.00 100.00');
 c.drawArmTrajectory({x:57,y:0},true);assert(c.$('xyzArmTrajectory').attrs.d.startsWith('M60.00'));
 c.drawArmTrajectory({x:100,y:50},true);assert.equal(c.$('xyzArmTrajectory').attrs.d,'M100.00 50.00L100.00 100.00');
 c.drawArmTrajectory({x:100,y:100},true);assert('hidden' in c.$('xyzArmTrajectory').attrs);
 c.drawArmTrajectory({x:100,y:95},true);assert('hidden' in c.$('xyzArmTrajectory').attrs);
});
test('route follows checked detours and does not erase when the marker is away from the route',()=>{
 const c=display();c.route([[0,0],[0,100],[200,100],[200,0]]);c.drawXYZ();
 const before=c.$('xyzArmTrajectory').attrs.d;c.drawArmTrajectory({x:100,y:0},true);
 assert.equal(c.$('xyzArmTrajectory').attrs.d,before);
 c.drawArmTrajectory({x:50,y:100},true);assert.equal(c.$('xyzArmTrajectory').attrs.d,'M50.00 100.00L200.00 100.00L200.00 0.00');
});
test('new route, mode/session/layout changes and stale feedback reset display interpolation',()=>{
 const c=display();c.drawXYZ();c.state.mobile_arm.tip.x=100;c.state.mobile_arm.position_at+=.2;c.frame();assert(c.displayedArmTip().x<100);
 c.state.mobile_arm.session='new';c.drawXYZ();assert.equal(c.displayedArmTip().x,100);
 c.route([[100,0],[200,0]]);c.drawXYZ();assert(!('hidden' in c.$('xyzArmTrajectory').attrs));
 c.state.mobile_arm.motion_path={id:'path-2',points:[{x:100,y:0},{x:100,y:100}]};c.drawXYZ();assert(c.$('xyzArmTrajectory').attrs.d.endsWith('L100.00 100.00'));
 c.now+=1600;c.drawXYZ();assert('hidden' in c.$('xyzArmTrajectory').attrs);
 c.state.mobile_arm.motion_path=null;c.lastFeed=c.now;c.drawXYZ();assert('hidden' in c.$('xyzArmTrajectory').attrs);
});
test('malformed paths are hidden and never become movement targets',()=>{
 for(const route of [null,{id:2,points:[{},{}]},{id:'bad',points:[{x:0,y:0},{x:NaN,y:1}]},{id:'bad',points:Array(2049).fill({x:0,y:0})}]){
  const c=display();c.state.mobile_arm.motion_path=route;c.drawXYZ();assert('hidden' in c.$('xyzArmTrajectory').attrs);assert.equal(c.xyzTarget.x,200);
 }
});
test('missing or malformed source timestamps fall back to current measured position',()=>{
 for(const stamp of [undefined,null,'2',NaN,Infinity]){
  const c=display();c.drawXYZ();c.state.mobile_arm.position_at=stamp;c.state.mobile_arm.tip.x=80;c.frame();
  assert.equal(c.displayedArmTip().x,80);
 }
});
