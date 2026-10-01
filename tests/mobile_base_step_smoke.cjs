/* Run: node tests/mobile_base_step_smoke.cjs. No browser or hardware. */
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const MobileJointRig=require('../shared/mobile_ltz/joint-rig.js');
const source=fs.readFileSync('shared/mobile_ltz/mobile.js','utf8');
const elements=new Map();
function element(id){
 if(!elements.has(id))elements.set(id,{attrs:{},dataset:{},amount:{},handlers:{},style:{setProperty(){}},querySelector(){return this.amount;},setAttribute(k,v){this.attrs[k]=v;},addEventListener(k,fn){this.handlers[k]=fn;}});
 return elements.get(id);
}
let ready=true;
const limits=[[-160,160],[-25,85],[-25,105]];
const ctx={$:element,MobileJointRig,jointControls:new MobileJointRig.JointControls(),jointFine:false,
 joints:[5.234,20,30],baseGoal:null,pendingJoints:false,controlMode:'joint',switchBusy:false,
 state:{virtual_play:false,mobile_arm:{limits}},document:{hidden:false},controlPointers:new Set(),mapPointers:new Map(),
 manualAvailable:()=>ready,jointBounds:axis=>limits[axis],sliderBounds:axis=>limits[axis]};
vm.createContext(ctx);
vm.runInContext(source.slice(source.indexOf('const jointStepButtons='),source.indexOf('function jointBounds('))+
 source.slice(source.indexOf('function updateJoints('),source.indexOf('let jointCaptionTop='))+
 source.slice(source.indexOf('function target('),source.indexOf("wheel.addEventListener('pointerdown'")),ctx);
const tap=id=>element(id).handlers.click();
tap('baseLeft');assert.equal(ctx.baseGoal,6.234);assert.equal(ctx.pendingJoints,true);
assert.deepEqual(ctx.joints,[6.234,20,30],'Only J1 changes');
assert.equal(element('wheel').attrs['aria-valuenow'],6.234,'Dial follows the step target');
assert.equal(element('j1Value').textContent,'6.2°');
assert.equal(element('baseSelector').attrs.transform,`rotate(${MobileJointRig.baseDialAngle(6.234,limits[0])} 120 136)`);
tap('baseLeft');assert.equal(ctx.baseGoal,7.234,'Rapid taps accumulate from the selected target');
ctx.state.mobile_arm.joints=[5.234,20,30];
ctx.jointFine=true;tap('baseRight');assert.ok(Math.abs(ctx.baseGoal-7.134)<1e-9,'Fine tune uses a 0.1-degree step');
assert.equal(element('baseRight').amount.textContent,'0.1°');
assert.equal(element('baseRight').attrs['aria-label'],'Rotate arm right by 0.1 degree');
ctx.jointFine=false;
ctx.baseGoal=null;ctx.joints[0]=159.7;tap('baseLeft');assert.equal(ctx.baseGoal,160,'Runtime limits clamp the final partial step');
ctx.pendingJoints=false;tap('baseLeft');assert.equal(ctx.pendingJoints,false,'Repeated taps at the limit do not requeue motion');
tap('baseRight');assert.equal(ctx.baseGoal,159,'Can retreat immediately from a limit');
// Shoulder and elbow steps retain independent goals while real feedback lags.
ctx.joints[2]=30.234;tap('j3Increase');assert.equal(ctx.jointControls.value(2,-99),31.234);
assert.equal(element('j3').value,31.234,'The matching range slider updates immediately');
tap('j2Decrease');assert.equal(ctx.jointControls.value(1,-99),19);assert.equal(ctx.jointControls.value(2,-99),31.234);
for(let i=0;i<3;i++)tap('j2Increase');assert.equal(ctx.jointControls.value(1,-99),22);
ctx.jointFine=true;tap('j3Decrease');tap('j2Increase');
assert.ok(Math.abs(ctx.jointControls.value(2,-99)-31.134)<1e-9);assert.ok(Math.abs(ctx.jointControls.value(1,-99)-22.1)<1e-9);
const emitted=ctx.jointControls.step(.016,[5.234,20,30.234],[limits[1],limits[2]],true);
assert.equal(emitted.length,2);assert.ok(Math.abs(emitted[0][1]-22.1)<1e-9);assert.ok(Math.abs(emitted[1][1]-31.134)<1e-9,'The existing physical follower receives both selected goals');
for(const blocked of ['unavailable','switching','hidden','other-mode','control-drag','map-drag']){
 ctx.pendingJoints=false;
 ready=blocked!=='unavailable';ctx.switchBusy=blocked==='switching';ctx.document.hidden=blocked==='hidden';
 ctx.controlMode=blocked==='other-mode'?'xyz':'joint';
 if(blocked==='control-drag')ctx.controlPointers.add(1);if(blocked==='map-drag')ctx.mapPointers.set(2,{});
 for(const id of ['baseLeft','baseRight','j2Decrease','j2Increase','j3Decrease','j3Increase'])tap(id);
 assert.equal(ctx.baseGoal,159,blocked);assert.equal(ctx.pendingJoints,false,blocked);
 assert.equal(ctx.jointControls.moving,false,blocked);assert.ok(Math.abs(ctx.jointControls.value(1,-99)-22.1)<1e-9,blocked);assert.ok(Math.abs(ctx.jointControls.value(2,-99)-31.134)<1e-9,blocked);
 ctx.controlPointers.clear();ctx.mapPointers.clear();
}
ready=true;ctx.switchBusy=false;ctx.document.hidden=false;ctx.controlMode='joint';
ctx.requestBase(NaN,0);assert.equal(ctx.baseGoal,159,'Invalid input is rejected');
ctx.requestBase(10.37);assert.equal(ctx.baseGoal,10.5,'The existing dial keeps its half-degree snapping');
for(const [axis,plus,minus,upper] of [[1,'j2Increase','j2Decrease',85],[2,'j3Increase','j3Decrease',105]]){
 ctx.jointControls.cancel();ctx.joints[axis]=upper-.05;tap(plus);assert.equal(ctx.jointControls.value(axis,-99),upper,'Clamp partial fine steps at the runtime limit');
 ctx.jointControls.step(.016,ctx.joints,[limits[1],limits[2]],true);tap(plus);assert.equal(ctx.jointControls.moving,false,'No repeated command at the limit');
 tap(minus);assert.ok(Math.abs(ctx.jointControls.value(axis,-99)-(upper-.1))<1e-9,'Immediate fine retreat from the limit');
}
console.log('PASS: J1/J2/J3 arrow steps use 1° or 0.1°, retain independent fractional targets, update their controls, share the guarded follower and reject unavailable/conflicting input');
