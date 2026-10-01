/* Pure UI command-queue checks; no robot/browser/network. */
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('shared/mobile_ltz/mobile.js','utf8'),handlers=new Map();
let ready=true;
const ctx={$:id=>({addEventListener:(event,fn)=>handlers.set(id,fn)}),
 manualAvailable:()=>ready,cartesian:()=>['xyz','targeting','cue'].includes(ctx.controlMode),updateXYZ(){},
 xyzTarget:{x:100.25,y:200.5,z:60.25},xyzFine:false,xyzEdit:0,xyzError:'',pendingXYZ:false,pendingXYZTarget:null,
 controlMode:'xyz',switchBusy:false,document:{hidden:false},controlPointers:new Set(),mapPointers:new Map(),viewport:{direction:1},
 state:{mobile_arm:{tip:{x:50,y:60,z:55},xyz_limits:{x:[0,1280],y:[0,720],z:[-150,230]}}}};
vm.createContext(ctx);
vm.runInContext(source.slice(source.indexOf('function xyzDirection('),source.indexOf('function cancelXYZ(')),ctx);
vm.runInContext(source.slice(source.indexOf('function requestXYZAxis('),source.indexOf("$('xyzPrecision').onclick")),ctx);
const tap=id=>handlers.get(id)();
tap('xyzXIncrease');tap('xyzXIncrease');tap('xyzYDecrease');
assert.deepEqual(ctx.xyzTarget,{x:120.25,y:190.5,z:60.25},'Rapid taps accumulate from fractional targets with delayed feedback');
ctx.xyzFine=true;tap('xyzXDecrease');tap('xyzZIncrease');
assert.deepEqual(ctx.xyzTarget,{x:119.25,y:190.5,z:60.35},'Fine tune divides X/Y/Z arrow increments by ten');
assert.deepEqual({...ctx.pendingXYZTarget},{x:50,y:60,z:60.35},'Height queues measured XY, not a preview destination');
for(const fine of [false,true]){
 ctx.viewport.direction=-1;ctx.xyzFine=fine;ctx.xyzTarget={x:100.25,y:200.5,z:60};
 tap('xyzXIncrease');tap('xyzYDecrease');tap('xyzZIncrease');
 assert.deepEqual(ctx.xyzTarget,{x:100.25-(fine?1:10),y:200.5+(fine?1:10),z:60+(fine?.1:1)},'Rotated XY follows screen arrows while height stays upright');
 tap('xyzXDecrease');tap('xyzYIncrease');tap('xyzZDecrease');
 assert.deepEqual(ctx.xyzTarget,{x:100.25,y:200.5,z:60},'Opposite arrows restore fractional goals');
}
ctx.viewport.direction=1;
for(const mode of ['targeting','cue']){
 ctx.controlMode=mode;ctx.pendingXYZ=false;
 tap('xyzXIncrease');tap('xyzYDecrease');assert(!ctx.pendingXYZ,'Manual XY arrows are XYZ-only');
 tap('xyzZDecrease');assert(ctx.pendingXYZ,mode+' supports idle height');
}
for(const [axis,upper,id] of [['x',1280,'xyzXIncrease'],['y',720,'xyzYIncrease'],['z',230,'xyzZIncrease']]){
 ctx.controlMode='xyz';ctx.xyzTarget[axis]=upper-.05;tap(id);assert.equal(ctx.xyzTarget[axis],upper);
 ctx.pendingXYZ=false;tap(id);assert(!ctx.pendingXYZ,'Do not repeatedly send motion at the bound');
}
ctx.viewport.direction=-1;
for(const [axis,id] of [['x','xyzXIncrease'],['y','xyzYIncrease']]){
 ctx.xyzTarget[axis]=.05;tap(id);assert.equal(ctx.xyzTarget[axis],0,'Rotated arrows clamp to the raw lower limit');
 ctx.pendingXYZ=false;tap(id);assert(!ctx.pendingXYZ,'Rotated bound does not resend motion');
}
for(const blocked of ['unavailable','switching','hidden','joint','control-drag','map-drag']){
 ready=blocked!=='unavailable';ctx.switchBusy=blocked==='switching';ctx.document.hidden=blocked==='hidden';ctx.controlMode=blocked==='joint'?'joint':'xyz';
 if(blocked==='control-drag')ctx.controlPointers.add(1);if(blocked==='map-drag')ctx.mapPointers.set(1,{});
 ctx.pendingXYZ=false;for(const id of handlers.keys())tap(id);assert(!ctx.pendingXYZ,blocked);
 ctx.controlPointers.clear();ctx.mapPointers.clear();
}
console.log('PASS: XYZ arrows follow both viewport orientations, use 10/10/1 or 1/1/0.1 increments, accumulate fractional targets, preserve XY for height, clamp limits and reject blocked input');
