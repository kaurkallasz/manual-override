// Ordinary and embedded player controls consume the actual Game projection.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('shared/robot_controls/controller.html','utf8');
const adapter=source.slice(source.indexOf("document.body.classList.toggle('mobileLtz'"),source.indexOf('function applyLtzProgress'));
const presentation=source.slice(source.indexOf('function applyLtxConfig('),source.indexOf('async function pollLtxConfig('));
const transport=source.slice(source.indexOf('async function api('),source.indexOf('function report('));
(async()=>{
 for(const side of ['green','purple'])for(const mobile of [false,true]){
  const elements=new Map(),calls=[];
  const gid=id=>{if(!elements.has(id))elements.set(id,{hidden:false,textContent:'',options:[1,2,3,4].map(value=>({value:String(value)}))});return elements.get(id);};
  const context=vm.createContext({LTX:true,LTZ:true,MOBILE_LTZ:mobile,TEAM:side,location:{search:'?ltz=1'+(mobile?'&mobile=1':'')},URLSearchParams,
   performance:{now:()=>1000},AbortSignal,AbortController,setTimeout,clearTimeout,
   document:{hidden:false,body:{classList:{toggle(){}}},querySelector:()=>gid('heading')},gid,
   requestAnimationFrame:()=>{},renderCraneControls(){},playerName:'',ltzTier:0,
   autoPpxRunning:false,autoPpxAbort:false,autoPpxClickOverride:null,ltxVideoClickEnabled:false,ltxGameMode:null,
   pauseUserMoves(){},cancelAutoPpxClickOverride(){},invalidateVideoClicks(){},armConnectBusy:false,log(){},BASE:'/fake/',
   fetch:async(url,opts)=>{calls.push({url,opts});return {json:async()=>({ok:true})};}});
  vm.runInContext(adapter+'\n'+presentation+'\n'+transport,context);
  for(let tier=1;tier<=4;tier++){
   context.input={contract:'photon.game',version:2,status:'ready',virtual_play:false,phase:'setup',virtual_test_control:tier,
    mobile_progress:{player:{id:side,name:'Pilot',current_control_tier:1}}};
   await vm.runInContext('applyMobileGame(input)',context);
   assert.equal(gid('mobilePhysicalControl').value,String(tier));
   assert.equal(gid('jointAnglesPanel').hidden,tier!==1);
   assert.equal(gid('tcpPosePanel').hidden,![2,3].includes(tier));
   assert.equal(gid('autoPickPlacePanel').hidden,tier!==3);
   assert.equal(gid('autoPpxPanel').hidden,tier!==4);
   const path=tier===1?'/api/joint-move':'/api/move';
   vm.runInContext('autoPpxRunning='+String(tier===4),context);
   const result=await vm.runInContext(`api('${path}',{ltz_action:'${['joint','xyz','image','cue'][tier-1]}'})`,context);
   assert(result.ok,side+' '+tier+' '+mobile);
   assert.equal(JSON.parse(calls.at(-1).opts.body).ltz_action,['joint','xyz','image','cue'][tier-1]);
  }
  context.input.virtual_test_control=null;context.input.mobile_progress.player.current_control_tier=2;
  vm.runInContext('autoPpxRunning=false',context);
  await vm.runInContext('applyMobileGame(input)',context);
  assert.equal(gid('mobilePhysicalControl').value,'2');
  assert.equal((await vm.runInContext("api('/api/joint-move',{})",context)).ok,false,'saved mandatory XYZ cannot use Joint');
  context.input.virtual_test_control=4;context.input.journey={phase:'calibration',active_side:side==='green'?'purple':'green'};
  await vm.runInContext('applyMobileGame(input)',context);
  assert.equal((await vm.runInContext("api('/api/move',{})",context)).ok,false,'practice cannot bypass another calibration owner');
 }
 console.log('PASS: ordinary and embedded Green/Purple controllers apply GM tiers 1–4, restore saved tiers, route commands and block calibration waiting');
})().catch(error=>{console.error(error);process.exitCode=1;});
