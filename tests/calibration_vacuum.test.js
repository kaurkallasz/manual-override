/* Actual disconnect/visibility and phone handlers with simulated hardware. */
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const controller=fs.readFileSync('shared/robot_controls/controller.html','utf8');
const mobile=fs.readFileSync('shared/mobile_ltz/mobile.js','utf8');
function fixture(team='green'){
 const calls=[],events={};
 const c={TEAM:team,LTZ:true,BASE:'/robot/',mobileOwnsMotion:true,autoPpxAbort:false,
  mobileGame:{virtual_play:false,journey:{phase:'calibration',calibration_side:team},mobile_calibration_connect:true,mobile_calibration:{stage:'points'}},
  playerJointStatus:{pump_mode:'suck'},pauseUserMoves(){calls.push({path:'cancel-motion'});},
  api(path,body){calls.push({path,body});return Promise.resolve({ok:true});},
  window:{addEventListener(name,fn){events[name]=fn;}},navigator:{sendBeacon(path,body){calls.push({path,body});}},Blob};
 vm.createContext(c);
 vm.runInContext(controller.slice(controller.indexOf('function mobileCalibrationKeepsSuction('),controller.indexOf('async function applyMobileGame(')),c);
 const pagehide=controller.indexOf('window.addEventListener("pagehide"');
 vm.runInContext(controller.slice(pagehide,controller.indexOf("window.addEventListener('message'",pagehide)),c);
 return {c,calls,events};
}
for(const team of ['green','purple']){
 test(team+' calibration holds motion and leaves suction on for disconnect/visibility/page exit',()=>{
  for(const stage of ['points','perspective','tutorial'])for(const kind of ['halt','pagehide']){
   const {c,calls,events}=fixture(team);c.mobileGame.mobile_calibration.stage=stage;
   if(kind==='halt')c.haltMobileRobot();else events.pagehide();
   assert(calls.some(c=>c.path.endsWith('stop')));
   assert(!calls.some(c=>c.path.includes('pump')));
   assert.equal(c.mobileOwnsMotion,false);assert.equal(c.autoPpxAbort,true);
  }
 });
 test(team+' gameplay, partner turn, completed calibration and blow retain pump-off cleanup',async()=>{
  const changes=[c=>c.mobileGame.journey.phase='playing',c=>c.mobileGame.journey.calibration_side=team==='green'?'purple':'green',
   c=>c.mobileGame.mobile_calibration.stage='complete',c=>c.mobileGame.mobile_calibration_connect=false,
   c=>c.mobileGame.virtual_play=true,c=>c.playerJointStatus.pump_mode='blow',c=>c.playerJointStatus.pump_mode='off',
   c=>delete c.playerJointStatus.pump_mode,c=>c.mobileGame=null];
  for(const change of changes)for(const kind of ['halt','pagehide']){
   const {c,calls,events}=fixture(team);change(c);
   if(kind==='halt')c.haltMobileRobot();else events.pagehide();
   const off=calls.find(c=>c.path.endsWith('pump'));assert(off);
   assert.equal((off.body instanceof Blob?JSON.parse(await off.body.text()):off.body).mode,'off');
  }
 });
 test(team+' phone Stop preserves the suction indicator and explains retention',async()=>{
  const {c}=fixture(team),sent=[],shown=[],notices=[];
  Object.assign(c,{team,state:c.mobileGame,confirmedPump:'suction',session:'physical:test',controllerId:'test',generation:0,
   joinRequest:null,joinWanted:true,connectionLog:{record(){}},preference:{set(){}},
   cancelXYZ(){},cancelJointSliders(){},showPump:mode=>shown.push(mode),renderControls(){},feedback:message=>notices.push(message),
   controlPointers:new Set(),mapPointers:new Map(),request:async(...args)=>sent.push(args)});
  vm.runInContext(mobile.slice(mobile.indexOf('function calibrationHoldsSuction('),mobile.indexOf('function keepJoined(')),c);
  await c.stop();
  assert.equal(c.session,null);assert.equal(c.confirmedPump,'suction');assert.equal(shown.at(-1),'suction');
  assert.match(notices.at(-1),/Suction kept on for calibration/);
  assert.equal(sent[0][1].action,'stop');assert.equal(sent[0][1].session,'physical:test');
  c.state.journey.phase='playing';c.clearInput();assert.equal(c.confirmedPump,'off');
 });
}
