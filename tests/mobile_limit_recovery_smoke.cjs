/* Run: node tests/mobile_limit_recovery_smoke.cjs. No browser or hardware. */
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('shared/mobile_ltz/mobile.js','utf8');
const recovery=source.slice(source.indexOf('function recoverMotionLimit('),source.indexOf('function clearInput('));
let now=100,cancelled=0,shown=[];
const box={replaceChildren:rows=>shown=rows};
const ctx={performance:{now:()=>now},document:{createElement:()=>({setAttribute(){}})},$:()=>box,
 session:'physical:one',generation:3,state:{virtual_play:false},pendingJoints:true,pendingXYZ:true,baseGoal:90,wheelDrag:{},controlPointers:new Set([1]),joints:[90,80,100],xyzTarget:{x:5,y:5,z:5},
 cancelXYZ(){ctx.pendingXYZ=false;cancelled++;},cancelJointSliders(){cancelled++;},updateJoints(){},updateXYZ(){},renderControls(){}};
vm.createContext(ctx);
const feedback=source.slice(source.indexOf('const feedbackLines='),source.indexOf('function syncViewport('));
vm.runInContext(feedback+recovery,ctx);
const error={code:'motion_limit',message:'Safety limit reached. Choose a target inside the red boundary.',arm:{connected:true,session:ctx.session,joints:[5,20,30],tip:{x:250,y:100,z:80}}};
assert(ctx.recoverMotionLimit(error));assert.equal(ctx.session,'physical:one');assert.equal(ctx.generation,3);assert.equal(ctx.pendingJoints,false);assert.equal(ctx.pendingXYZ,false);assert.equal(ctx.baseGoal,null);assert.equal(ctx.wheelDrag,null);assert.equal(ctx.controlPointers.size,0);assert.equal(cancelled,2);assert.deepEqual(Array.from(ctx.joints),[5,20,30]);assert.deepEqual({...ctx.xyzTarget},error.arm.tip);
vm.runInContext("feedback('Routine telemetry')",ctx);assert.equal(shown.textContent,error.message,'Routine status cannot immediately overwrite the rejection');
now+=7999;vm.runInContext("feedback('Connected')",ctx);assert.equal(shown.textContent,error.message);
now+=2;vm.runInContext("feedback('Connected')",ctx);assert.equal(shown.textContent,'Connected');
for(const bad of [{...error,code:undefined},{...error,arm:{...error.arm,connected:false}},{...error,arm:{...error.arm,session:'physical:other'}}])assert(!ctx.recoverMotionLimit(bad),'Do not retain a missing, foreign, or failed connection');
const missingAtom={...error,code:'target_unavailable',message:'Selected Atom moved. Select its current position and press Go again.'};
ctx.pendingXYZ=true;ctx.xyzTarget={x:300,y:200,z:80,tag_id:100};
assert(ctx.recoverMotionLimit(missingAtom));assert.equal(ctx.session,'physical:one');assert.equal(ctx.generation,3);assert.equal(ctx.pendingXYZ,false);assert.equal(ctx.xyzTarget.tag_id,undefined);assert.equal(shown.textContent,missingAtom.message);
for(const bad of [{...missingAtom,arm:null},{...missingAtom,arm:{...error.arm,connected:false}},{...missingAtom,arm:{...error.arm,session:'physical:other'}}])assert(!ctx.recoverMotionLimit(bad));
console.log('PASS: boundary and Atom rejection clear movement goals without disconnecting; eight-second readable notice; genuine faults remain fail-closed');
