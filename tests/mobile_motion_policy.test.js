/* Player and embedded controller must honor the same server decision. No I/O. */
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const mobile=fs.readFileSync('shared/mobile_ltz/mobile.js','utf8');
const controller=fs.readFileSync('shared/robot_controls/controller.html','utf8');
function context(policy){
 const game={status:'ready',phase:'setup',virtual_play:false,virtual_test_control:null,
  journey:{phase:'lobby'},mobile_motion_policy:policy,mobile_safety:{status:'ready'}};
 const c={state:game,mobileGame:game,mobileGameAt:100,performance:{now:()=>100},document:{hidden:false},mobileViewActive:true,mobileCalibrationLoading:null};
 vm.createContext(c);
 vm.runInContext(mobile.slice(mobile.indexOf('function transitionAllowsControls()'),mobile.indexOf('function canJoin()')),c);
 vm.runInContext(controller.slice(controller.indexOf('function mobileMotionPolicyReady()'),controller.indexOf('function mobileCalibrationKeepsSuction(')),c);
 return c;
}
const ready=()=>({contract:'photon.game.motion',version:1,status:'ready',scope:'player',tier:null,blocked:false,error:null});
test('event setup permits controls only when the server grants motion',()=>{
 const c=context(ready());assert(c.transitionAllowsControls());assert(c.mobileConnectionReady());assert(c.mobileRobotReady());
 c.state.mobile_motion_policy={...ready(),blocked:true,error:'Waiting for Game Master to start the next match'};
 assert(!c.transitionAllowsControls());assert(!c.mobileConnectionReady());assert(!c.mobileRobotReady());
 assert.equal(c.transitionControlError(),'Waiting for Game Master to start the next match');
});
test('absent, invalid, unavailable and waiting policies cannot enable browser controls',()=>{
 for(const p of [undefined,null,{...ready(),contract:'wrong'},{...ready(),version:true},{...ready(),version:2},
  {...ready(),status:'unavailable'},{...ready(),blocked:undefined},{...ready(),scope:'waiting'},{...ready(),scope:'practice'}]){
  const c=context(p);assert(!c.transitionAllowsControls());assert(!c.mobileRobotReady());
 }
});
test('calibration recovery may connect but cannot move before owner grants motion',()=>{
 const c=context({...ready(),scope:'waiting',blocked:true,error:'Previous stop unconfirmed'});
 c.state.journey={phase:'calibration',calibration_side:'green'};c.state.mobile_calibration_connect=true;
 assert(c.mobileConnectionReady());assert(!c.mobileRobotReady());assert(!c.transitionAllowsControls());
 c.state.mobile_calibration_ready=true;assert(!c.mobileRobotReady());
 c.state.mobile_motion_policy={...ready(),scope:'tutorial',tier:2};assert(c.mobileRobotReady());
 c.state.mobile_calibration_connect=false;assert(!c.mobileConnectionReady());assert(!c.mobileRobotReady());
});
test('authoritative permission never overrides feedback preparation, pause, visibility or game freshness',()=>{
 for(const change of [c=>c.state.paused=true,c=>c.document.hidden=true,c=>c.mobileGameAt=-3000,
  c=>c.state.mobile_safety.status='unavailable',c=>c.state.phase='won',c=>c.state.virtual_play=true]){
  const c=context(ready());change(c);assert(!c.mobileRobotReady());
 }
});
