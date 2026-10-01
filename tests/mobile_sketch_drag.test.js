'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const {JointDrag,JointControls,mount,bearing}=require('../shared/mobile_ltz/joint-rig.js');
const polar=(pivot,angle,radius=175,offset=0)=>({x:pivot.x+radius*Math.cos(angle*Math.PI/180),y:pivot.y+radius*Math.sin(angle*Math.PI/180)+offset});
test('elbow drag selects J2 and nozzle drag selects J3 with the MG400 bearing direction',()=>{
 for(const axis of [1,2]){
  const drag=new JointDrag(),pivot={x:300,y:400},offset=axis===2?51:0,value=30,start=polar(pivot,bearing(axis,value),175,offset);
  assert(drag.begin(axis,value,start.x,start.y,pivot,offset,[-25,85]));
  const next=polar(pivot,bearing(axis,40),175,offset);
  assert.ok(Math.abs(drag.move(next.x,next.y)-40)<1e-9);
  assert.equal(drag.axis,axis);
 }
});
test('touch-down does not jump to an existing target; precision is tenfold and wrap is continuous',()=>{
 const pivot={x:300,y:400},start=polar(pivot,150,175,51),next=polar(pivot,140,175,51);
 for(const [fine,expected] of [[false,60],[true,51]]){
  const drag=new JointDrag();assert(drag.begin(2,50,start.x,start.y,pivot,51,[-25,105],fine));
  assert.equal(drag.move(start.x+1,start.y+1),null);assert.equal(drag.value,50);
  assert.ok(Math.abs(drag.move(next.x,next.y)-expected)<1e-9);
 }
 const drag=new JointDrag(),a=polar(pivot,179),b=polar(pivot,-179);
 drag.begin(2,0,a.x,a.y,pivot,0,[-25,105]);assert.ok(Math.abs(drag.move(b.x,b.y)+2)<1e-9);
});
test('limits clamp without windup and crossing the pivot cannot cause an angle jump',()=>{
 const drag=new JointDrag(),pivot={x:100,y:100},start=polar(pivot,100);
 drag.begin(1,84,start.x,start.y,pivot,0,[-25,85]);
 let p=polar(pivot,80);assert.equal(drag.move(p.x,p.y),85);
 p=polar(pivot,85);assert.ok(Math.abs(drag.move(p.x,p.y)-80)<1e-9,'retreat responds immediately');
 assert.equal(drag.move(pivot.x,pivot.y),null);
 p=polar(pivot,-70);assert.equal(drag.move(p.x,p.y),null,'rebase after crossing the center');assert.ok(Math.abs(drag.value-80)<1e-9);
 drag.cancel();assert.equal(drag.move(0,0),null);
 for(const bounds of [null,{},[0,0],[0,NaN]])assert.equal(drag.begin(1,0,100,200,pivot,0,bounds),false);
});
test('captured sketch gestures use JointControls, retain the other slider, and cancel on unavailable feedback',()=>{
 const originalRaf=global.requestAnimationFrame,originalCancel=global.cancelAnimationFrame;let frame;
 global.requestAnimationFrame=fn=>{frame=fn;return 1;};global.cancelAnimationFrame=()=>{};
 const parts=new Map(),captured=new Set(),active=new Set();
 const part=()=>({attrs:{},style:{},listeners:{},classList:{toggle(){}},setAttribute(k,v){this.attrs[k]=v;},
  addEventListener(k,fn){this.listeners[k]=fn;},focus(){},setPointerCapture(id){captured.add(id);},hasPointerCapture(id){return captured.has(id);},releasePointerCapture(id){captured.delete(id);}});
 const host={...part(),clientWidth:360,clientHeight:300,getBoundingClientRect:()=>({left:100,top:100,width:360,height:300}),querySelector(key){if(!parts.has(key))parts.set(key,part());return parts.get(key);}};
 const controls=new JointControls(),state={physical:true,joints:[0,20,30],targets:[0,20,30],limits:[[-160,160],[-25,85],[-25,105]]};
 let available=true,cancelled=0,requests=[];
 try{
  const rig=mount(host,{state:()=>state,available:()=>available,goal:axis=>controls.value(axis,state.joints[axis]),
   previewTargets:()=>controls.preview(state.joints),
   begin:(axis,id)=>{if(active.size)return false;active.add(id);return true;},end:id=>active.delete(id),cancel:()=>{cancelled++;controls.cancel();},
   request:(axis,value)=>{requests.push([axis,value]);controls.request(axis,state.joints[axis],value);}});
  frame(16);
  const nozzle=parts.get('[data-rig-axis="2"]'),elbow=parts.get('[data-rig-axis="1"]');
  assert.match(nozzle.attrs['aria-valuetext'],/30.0 degrees target/);
  const e=(id,x,y,key)=>({pointerId:id,button:0,clientX:x,clientY:y,key,preventDefault(){},stopPropagation(){}});
  const point=button=>({x:100+parseFloat(button.style.left),y:100+parseFloat(button.style.top)});
  const start=point(nozzle);nozzle.listeners.pointerdown(e(1,start.x,start.y));assert(captured.has(1));assert.equal(requests.length,0);
  const other=point(elbow);elbow.listeners.pointerdown(e(2,other.x,other.y));assert(!captured.has(2));
  const pivot={...other},offset=start.y-pivot.y-175*Math.sin(150*Math.PI/180)*Number(parts.get('.rigForearm').attrs.transform.match(/scale\(([^)]+)\)/)[1]);
  const radius=Math.hypot(start.x-pivot.x,start.y-pivot.y-offset),next=polar(pivot,140,radius,offset);
  const red2=parts.get('.rigActualJ2').attrs.d,red3=parts.get('.rigActualJ3').attrs.d;
  nozzle.listeners.pointermove(e(1,next.x,next.y));
  assert.equal(requests[0][0],2);assert.ok(Math.abs(controls.value(2,-99)-40)<1e-8);assert.equal(controls.value(1,20),20);
  frame(32);
  assert.ok(Math.abs(Number(parts.get('.rigForearm').attrs.transform.match(/rotate\(([^)]+)\)/)[1])-140)<1e-8,'White sketch reaches J3 target on the first frame, before issuing motion');
  assert.ok(Math.abs(point(nozzle).x-next.x)<1e-8&&Math.abs(point(nozzle).y-next.y)<1e-8,'Nozzle follows the captured finger immediately');
  assert.equal(parts.get('.rigActualJ2').attrs.d,red2);assert.equal(parts.get('.rigActualJ3').attrs.d,red3,'Real-arm outline does not advance with a drag');
  assert.deepEqual(controls.step(.016,state.joints,[state.limits[1],state.limits[2]],true).map(([axis,value])=>[axis,Math.round(value)]),[[2,40]],'same physical follower receives the goal');
  assert.ok(Math.abs(Number(nozzle.attrs['aria-valuenow'])-40)<1e-8);
  nozzle.listeners.pointerup(e(1,next.x,next.y));assert.equal(captured.size,0);assert.equal(active.size,0);
  elbow.listeners.keydown(e(null,0,0,'ArrowUp'));assert.equal(controls.value(1,20),20.5);assert.ok(Math.abs(controls.value(2,30)-40)<1e-8);
  frame(40);assert.equal(Number(parts.get('.rigShoulder').attrs.transform.match(/rotate\(([^)]+)\)/)[1]),-110.5,'J2 target also draws immediately');
  assert.equal(parts.get('.rigActualJ2').attrs.d,red2);
  elbow.listeners.pointerdown(e(3,other.x,other.y));assert(captured.has(3));available=false;frame(48);
  assert.equal(captured.size,0);assert.equal(active.size,0);assert.equal(cancelled,1);assert.equal(controls.moving,false);assert(nozzle.disabled&&elbow.disabled);
  const count=requests.length;nozzle.listeners.pointerdown(e(4,start.x,start.y));nozzle.listeners.pointermove(e(4,next.x,next.y));nozzle.listeners.keydown(e(null,0,0,'End'));assert.equal(requests.length,count,'disabled feedback never issues a target');
  rig.destroy();
 }finally{global.requestAnimationFrame=originalRaf;global.cancelAnimationFrame=originalCancel;}
});
