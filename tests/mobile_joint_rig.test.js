'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const {pose,layout,Motion,IndicatorMotion,JointControls,delta,displayAngles,mount}=require('../sandboxes/green/prototypes/mobile-ltz/joint-rig.js');
const {sliderBounds,alignRight}=require('../sandboxes/green/prototypes/mobile-ltz/joint-rig.js');
test('fine sliders zoom exactly tenfold around each target and preserve width at physical limits',()=>{
 for(const bounds of [[-25,85],[-25,105],[-10,20]]){
  const span=(bounds[1]-bounds[0])/10;
  for(const center of [bounds[0],-5,0,bounds[1]]){
   const [lo,hi]=sliderBounds(bounds,center,true);
   assert.ok(Math.abs(hi-lo-span)<1e-9);assert.ok(lo>=bounds[0]&&hi<=bounds[1]);
   assert.ok(center>=lo&&center<=hi);
   assert.deepEqual(sliderBounds(bounds,center,false),bounds);
  }
 }
 assert.deepEqual(sliderBounds([-25,85],-5,true),[-10.5,.5]);
 assert.deepEqual(sliderBounds([-25,105],-5,true),[-11.5,1.5]);
});
test('actual indicator moves between sparse packets with continuous velocity',()=>{
 const indicator=new IndicatorMotion();indicator.reset(0);let previous=0,previousStep=0;
 for(let frame=1;frame<=180;frame++){
  const target=Math.floor(frame/10)*2,value=indicator.step(target,1/60),step=value-previous;
  assert.ok(value>=previous&&value<=target);
  if(frame>30){assert.ok(step>.15,'continues moving between packets');assert.ok(Math.abs(step-previousStep)<.045,'new packets do not kick velocity');}
  previous=value;previousStep=step;
 }
});
test('actual indicator converges without overshoot and reverses within confirmed bounds',()=>{
 const indicator=new IndicatorMotion();indicator.reset(-25);
 for(const target of [85,-25,0]){
  let previous=indicator.value;
  for(let frame=0;frame<180;frame++){
   const value=indicator.step(target,1/60);
   assert.ok(value>=-25-1e-10&&value<=85+1e-10);
   if(frame>20)assert.ok(Math.abs(target-value)<=Math.abs(target-previous)+1e-10);
   previous=value;
  }
  assert.ok(Math.abs(indicator.value-target)<1e-8);
 }
});
test('indicator smoothing is frame-rate independent and each joint has its own state',()=>{
 const at=rate=>{const m=new IndicatorMotion();m.reset(0);for(let i=0;i<rate;i++)m.step(80,1/rate);return m.value;};
 assert.ok(Math.abs(at(30)-at(120))<1e-10);
 const j2=new IndicatorMotion(),j3=new IndicatorMotion();j2.reset(0);j3.reset(20);
 j2.step(85,.02);assert.equal(j3.step(20,.02),20);
});
test('indicator resets across invalid telemetry, suspension and long frame gaps',()=>{
 const indicator=new IndicatorMotion();assert.equal(indicator.step(12,.016),12);
 assert.equal(indicator.step(NaN,.016),null);assert.equal(indicator.step(24,.016),24);
 assert.equal(indicator.step(30,.016,false),30);
 assert.equal(indicator.step(-5,1),-5);
});
test('J3 moves head around fixed elbow, J2 carries elbow without changing absolute forearm angle',()=>{
 const home=pose(-5,-5),head=pose(-5,20),elbow=pose(20,-5);
 assert.deepEqual(home.elbow,head.elbow);assert.notDeepEqual(home.head,head.head);
 assert.equal(home.b,elbow.b);assert.notDeepEqual(home.elbow,elbow.elbow);
 for(const p of [home,head,elbow]){assert.ok(Math.abs(Math.hypot(p.elbow.x,p.elbow.y)-180)<1e-8);assert.ok(Math.abs(Math.hypot(p.wrist.x-p.elbow.x,p.wrist.y-p.elbow.y)-175)<1e-8);assert.equal(p.head.x,p.wrist.x);assert.equal(p.head.y-p.wrist.y,42);}
});
test('fixed half-height frame keeps handles attached and reachable through the full sweep',()=>{
 for(const [w,h] of [[362,422],[292,284],[475,195],[302,160]]){
  const frame=layout(w,h,[[-25,85],[-25,105]]);
  for(let j2=-25;j2<=85;j2+=2)for(let j3=-25;j3<=105;j3+=2){
   const p=pose(j2,j3);
   for(const point of [p.elbow,p.head]){
    const x=frame.x+point.x*frame.scale,y=frame.y+point.y*frame.scale;
    assert.ok(x>=24&&x<=w-24,`x ${x} in ${w}`);assert.ok(y>=24&&y<=h-24,`y ${y} in ${h}`);
   }
  }
 }
});
test('telemetry discontinuity cancels the gesture instead of jumping toward the new pose',()=>{
 const m=new Motion();m.begin(2,0,0,0,0);m.move(120,100,0,false);m.step(.02,0,[-25,105]);
 const before=m.value;assert.equal(m.step(.02,40,[-25,105]),null);assert.equal(m.axis,null);assert.equal(m.value,before);
});
test('touch threshold and angle wrap prevent jumps; head and elbow have calibrated direction',()=>{
 assert.equal(delta(-179,179),2);assert.equal(delta(179,-179),-2);
 const m=new Motion();m.begin(2,-5,179,0,0);m.move(-179,2,0,false);assert.equal(m.step(.02,-5,[-25,105]),null);
 m.move(-179,5,0,false);assert.equal(m.desired,-4);
 m.begin(1,-5,179,0,0);m.move(-179,5,0,false);assert.equal(m.desired,-6);
});
test('slew never exceeds 12 degrees/s, eases in, and limits target lead under latency',()=>{
 const m=new Motion();m.begin(2,0,0,0,0);m.move(120,100,0,false);let confirmed=0,last=0;
 for(let i=0;i<60;i++){const v=m.step(1/60,confirmed,[-25,105]);if(v!=null){assert.ok(v-last<=12/60+1e-8);if(!i)assert.ok(v<.02);confirmed=v;last=v;}}
 assert.ok(last>10&&last<=12);
 m.begin(2,0,0,0,0);m.move(120,100,0,false);for(let i=0;i<1000;i++)m.step(.016,0,[-25,105]);assert.equal(m.value,1.2);
 m.cancel();assert.equal(m.step(.016,0,[-25,105]),null);assert.equal(m.axis,null);
});
test('precision sensitivity, runtime limits and stale-frame dt cap',()=>{
 const m=new Motion();m.begin(2,104.9,0,0,0);m.move(60,100,0,true);assert.equal(m.desired,113.9);
 for(let i=0;i<100;i++)m.step(.016,104.9,[-25,105]);assert.equal(m.value,105);
 m.begin(1,-24.9,0,0,0);m.move(60,100,0,false);for(let i=0;i<100;i++)m.step(.016,-24.9,[-25,85]);assert.equal(m.value,-25);
 m.begin(2,0,0,0,0);m.move(60,100,0,false);const v=m.step(100,0,[-25,105]);assert.ok(v<=.15+1e-8);
});
test('slider requests slew toward selected angles and retarget the chosen axis',()=>{
 const m=new Motion();m.request(1,-5,20);let confirmed=-5;
 for(let i=0;i<200;i++){const before=confirmed,next=m.step(.02,confirmed,[-25,85]);if(next!==null){assert.ok(next-before<=.24+1e-8);confirmed=next;}}
 assert.equal(confirmed,20);m.request(2,-5,5);assert.equal(m.axis,2);assert.equal(m.value,-5);assert.equal(m.desired,5);
 m.cancel();assert.equal(m.step(.02,-5,[-25,105]),null);
});
test('arm illustration follows confirmed telemetry and exposes no input controls',()=>{
 const originalRaf=global.requestAnimationFrame,originalCancel=global.cancelAnimationFrame;let frame;
 global.requestAnimationFrame=fn=>{frame=fn;return 1;};global.cancelAnimationFrame=()=>{};
 const parts=new Map();const part=()=>({attrs:{},innerHTML:'',classList:{toggle(){}},setAttribute(k,v){this.attrs[k]=v;}});
 const host={...part(),clientWidth:360,clientHeight:300,getBoundingClientRect:()=>({width:360,height:300}),querySelector(key){if(!parts.has(key))parts.set(key,part());return parts.get(key);}};
 let preview=null,state={joints:[-80,-5,-5],targets:[-80,-5,-5],limits:[[-160,160],[-25,85],[-25,105]]};
 try{
  const rig=mount(host,{state:()=>state,available:()=>true,previewTargets:()=>preview});frame(16);
  assert.ok(!host.innerHTML.includes('<button'));assert.ok(!host.innerHTML.includes('<input'));assert.ok(host.innerHTML.includes('role="img"'));
  const before=parts.get('.rigShoulder').attrs.transform;
  const renderedScale=Number(before.match(/scale\(([^)]+)\)/)[1]);
  assert.equal(renderedScale,2*layout(360,300,[[-25,85],[-25,105]]).scale);
  const base=()=>parts.get('.rigShoulder').attrs.transform.match(/^translate\(([^)]+)\)/)[1];
  const fixedBase=base();
  const originalHeight=base().split(' ')[1];
  state.limits=[[-180,180],[-180,180],[-180,180]];frame(20);
  assert.equal(base().split(' ')[1],originalHeight,'expanded virtual reach keeps the shoulder above the slider dock');
  state.limits=[[-160,160],[-25,85],[-25,105]];frame(24);
  state.targets[1]=30;frame(32);assert.equal(parts.get('.rigShoulder').attrs.transform,before);
  state.joints[1]=10;frame(48);assert.notEqual(parts.get('.rigShoulder').attrs.transform,before);assert.equal(base(),fixedBase,'telemetry cannot move the base');
  const red2=parts.get('.rigActualJ2').attrs.d,red3=parts.get('.rigActualJ3').attrs.d;
  const vector=d=>{const [x,y,u,v]=d.match(/-?\d+(?:\.\d+)?/g).map(Number);return [+(u-x).toFixed(6),+(v-y).toFixed(6)];};
  assert.match(red2,/^M.+ L/);assert.match(red3,/^M.+ L/);
  // Slider endpoints must animate the entire pose even while telemetry stays still.
  for(const [j2,j3,shoulderAngle,forearmAngle] of [[85,105,-35,290],[-25,-25,-145,160]]){
   preview=[-80,j2,j3];for(let i=0;i<60;i++){frame(64+i*16+(j2<0?960:0));assert.equal(base(),fixedBase,'slider animation cannot move the base');}
   const angle=key=>Number(parts.get(key).attrs.transform.match(/rotate\(([^)]+)\)/)[1]);
   assert.ok(Math.abs(angle('.rigShoulder')-shoulderAngle)<.01);assert.ok(Math.abs(angle('.rigForearm')-forearmAngle)<.01);
   assert.match(parts.get('svg').attrs['aria-label'],/^Target preview:/);
   assert.equal(parts.get('.rigActualJ2').attrs.d,red2);assert.equal(parts.get('.rigActualJ3').attrs.d,red3);
  }
  state.joints[2]=25;frame(1990);assert.deepEqual(vector(parts.get('.rigActualJ2').attrs.d),vector(red2));assert.notDeepEqual(vector(parts.get('.rigActualJ3').attrs.d),vector(red3));
  preview=null;for(let i=0;i<60;i++)frame(2000+i*16);
  assert.match(parts.get('svg').attrs['aria-label'],/^Arm position:/);rig.destroy();
 }finally{global.requestAnimationFrame=originalRaf;global.cancelAnimationFrame=originalCancel;}
});
test('editing either slider preserves the other goal, preview and command progression',()=>{
 const controls=new JointControls(),confirmed=[-80,-5,-5],bounds=[[-25,85],[-25,105]];
 controls.request(1,-5,85);for(let i=0;i<10;i++)controls.step(.02,confirmed,bounds);
 const command2=controls.commanded(1,-99);
 controls.request(2,-5,105);
 assert.equal(controls.value(1,-99),85);assert.equal(controls.commanded(1,-99),command2);
 assert.deepEqual(controls.preview(confirmed),[-80,85,105]);
 confirmed[1]=command2; // The delayed acknowledgement catches up to the issued J2 command.
 for(let i=0;i<1500;i++)for(const [axis,value] of controls.step(.02,confirmed,bounds))confirmed[axis]=value;
 assert.ok(Math.abs(confirmed[1]-85)<1e-8);assert.ok(Math.abs(confirmed[2]-105)<1e-8);assert.equal(controls.moving,false);
 // An older packet cannot roll completed slider goals/commands back.
 assert.equal(controls.value(1,20),85);assert.ok(Math.abs(controls.commanded(1,20)-85)<1e-8);
 controls.request(1,85,-25);assert.deepEqual(controls.preview([-80,20,30]),[-80,-25,105]);
 controls.request(2,105,-25);assert.deepEqual(controls.preview(confirmed),[-80,-25,-25]);
 controls.cancel();assert.equal(controls.moving,false);assert.equal(controls.preview(confirmed),null);
});
test('small out-of-order telemetry pauses commands without dropping the slider goal',()=>{
 const controls=new JointControls(),bounds=[[-25,85],[-25,105]];
 controls.request(1,0,85);for(let i=0;i<60;i++)controls.step(.02,[-80,0,0],bounds);
 assert.equal(controls.commanded(1,0),1.2);
 assert.deepEqual(controls.step(.02,[-80,-.2,0],bounds),[]);assert.equal(controls.value(1,0),85);
 const updates=controls.step(.02,[-80,.4,0],bounds);assert.equal(updates.length,1);assert.ok(updates[0][1]>1.2);
});
test('preview uses the entire runtime range, clamps endpoints, and rejects invalid values',()=>{
 const current=[-80,-5,-5],bounds=[[-25,85],[-25,105]];
 assert.deepEqual(displayAngles(current,[-80,-25,105],bounds),[-80,-25,105]);
 assert.deepEqual(displayAngles(current,[-80,999,-999],bounds),[-80,85,-25]);
 assert.deepEqual(displayAngles(current,[-80,NaN,105],bounds),current);
 assert.deepEqual(displayAngles(current,null,bounds),current);
 assert.deepEqual(current,[-80,-5,-5]);
});

test('stationary shoulder half-circle aligns with the slider panel edge at 2x size',()=>{
 for(const [w,h,right] of [[242,372,228],[198,234,184],[405,195,391]]){
  const bounds=[[-25,85],[-25,105]],original=layout(w,h,bounds,2),frame=alignRight(original,bounds,right);
  const radius=Math.min(86,h*.38,180*frame.scale*.42);
  assert.ok(Math.abs(frame.x+radius-right)<1e-8);
  assert.equal(frame.scale,original.scale);assert.equal(frame.y,original.y);
 }
});

test('fixed base dial maps the full runtime range and preserves clockwise direction',()=>{
 const {baseDialAngle,baseDialValue}=require('../sandboxes/green/prototypes/mobile-ltz/joint-rig.js');
 for(const bounds of [[-160,160],[-90,120]]){
  assert.equal(baseDialAngle(bounds[0],bounds),90);assert.equal(baseDialAngle(bounds[1],bounds),-90);
  for(let i=0;i<=100;i++){
   const value=bounds[0]+(bounds[1]-bounds[0])*i/100;
   assert.ok(Math.abs(baseDialValue(baseDialAngle(value,bounds),bounds)-value)<1e-9);
  }
  assert.ok(baseDialValue(45,bounds)<baseDialValue(0,bounds));
  assert.equal(baseDialValue(180,bounds),bounds[0]);assert.equal(baseDialValue(-180,bounds),bounds[1]);
  assert.equal(baseDialAngle(bounds[1]+99,bounds),-90);
 }
});

test('increasing J2 swings the elbow right without translating the base or changing J3',()=>{
 let previous=pose(-25,10);
 for(let j2=-24;j2<=85;j2++){
  const current=pose(j2,10);
  assert.ok(current.elbow.x>previous.elbow.x);
  assert.deepEqual(current.shoulder,{x:0,y:0});assert.equal(current.b,previous.b);
  previous=current;
 }
});
