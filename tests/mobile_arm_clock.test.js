/* Real bridge and command handler with simulated feedback; no hardware or network. */
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('shared/mobile_ltz/arm-bridge.js','utf8');
const flush=async()=>{for(let i=0;i<12;i++)await new Promise(resolve=>setImmediate(resolve));};

async function bridge(team='green',offset=0){
 const clock={now:100,server:1792588055,offset},calls=[],posted=[],intervals=[],nodes=new Map();let listener,id=0;
 const parent={postMessage:value=>posted.push(value)};
 let robot={connected:true,enabled:true,feedback_ok:true,last_feedback:clock.server-.02,
  robot_mode:5,motion_ready:true,motion_epoch:1,control_session:'relay-1',
  pose:[300,100,50,9],joints:[0,20,30,9],pump_mode:'off'};
 const c={TEAM:team,MOBILE_LTZ:true,URLSearchParams,location:{search:'?bridge=1',origin:'http://test'},parent,
  window:{addEventListener:(name,fn)=>{listener=fn;}},performance:{now:()=>clock.now},
  Date:{now:()=>clock.server*1000+clock.offset},crypto:{getRandomValues:a=>a.fill(1)},setInterval:fn=>intervals.push(fn),
  gid:name=>{if(!nodes.has(name))nodes.set(name,{value:'http://test',checked:false,textContent:'',removeAttribute(){}});return nodes.get(name);},
  mobileGameAt:clock.now,mobileGame:{server_time:clock.server,phase:'setup',journey:{phase:'calibration'},
   mobile_calibration_connect:true,mobile_calibration:{stage:'points'},mobile_safety:{status:'ready'}},
  mobileConnectionReady:()=>!!c.mobileGame&&Number.isFinite(c.mobileGameAt)&&clock.now-c.mobileGameAt>=0&&clock.now-c.mobileGameAt<2000,mobileRobotReady:()=>true,mobileCalibrationKeepsSuction:()=>false,
  ws:{x:[-400,400],y:[-400,400],z:[-100,100]},jointLimits:{j1:[-160,160],j2:[-25,85],j3:[-25,105]},
  pauseUserMoves(){},cancelAutoPpxClickOverride(){},applyStatus(){},autoPpxAbort:false,
  autoPpxCueRunning:false,autoPpxPaused:false,autoPpxVisionWait:null,autoPpxCueError:null,activeOperation:null,cal2BoundaryStop:null,
  autoPpxCueDisplayTags:()=>[],autoPpxCueCandidates:()=>({sources:[],destinations:[]}),
  api:async(path,data)=>{calls.push({path,data});if(path==='/api/status'){clock.now+=clock.requestMs||0;return {feedback_observed_at:clock.server,...robot};}return {ok:true,control_session:robot.control_session};}};
 vm.createContext(c);vm.runInContext(source,c);await flush();
 return {clock,c,calls,posted,
  state:()=>posted.findLast(p=>p.type==='state'),
  async command(action='connect'){
   const key=String(++id);listener({source:parent,origin:'http://test',data:{contract:team+'.mobile-arm',version:1,type:'command',id:key,data:{action}}});
   await flush();return posted.findLast(p=>p.id===key);
  },
  async publish(fields={}){robot={...robot,...fields};c.applyStatus(await c.api('/api/status'));await flush();},
  async advance(ms,{game=true,feedback=true}={}){
   clock.now+=ms;clock.server+=ms/1000;
   if(game){c.mobileGame.server_time=clock.server;c.mobileGameAt=clock.now;}
   if(feedback)robot={...robot,last_feedback:clock.server-.02};
   // Keep the parent alive so feedback, rather than its heartbeat, is under test.
   listener({source:parent,origin:'http://test',data:{contract:team+'.mobile-arm',version:1,type:'ping'}});
   c.applyStatus(await c.api('/api/status'));intervals.forEach(fn=>fn());await flush();
  }};
}

test('both teams connect with phone clocks ahead or behind, without issuing a move',async()=>{
 for(const team of ['green','purple'])for(const offset of [0,2200,-2200,300000,-300000]){
  const b=await bridge(team,offset),reply=await b.command();
  assert.equal(reply.ok,true,`${team}, clock offset ${offset}: ${reply.error}`);
  assert(reply.arm.session);assert.equal(reply.arm.motion_ready,true);
  assert.equal(reply.arm.position_at,b.clock.server-.02,'Keep the measured source timestamp');
  assert(Math.abs(reply.diagnostics.feedback_age_ms-20)<.01);
  assert.deepEqual(b.calls.filter(x=>x.path!=='/api/status').map(x=>x.path),['/api/connect']);
 }
});

test('phone wall-clock changes cannot drop a healthy connected arm',async()=>{
 const b=await bridge();const reply=await b.command(),session=reply.arm.session;
 for(const offset of [3600000,-3600000,2200]){
  b.clock.offset=offset;await b.advance(100);
  assert.equal(b.state().arm.session,session);assert.equal(b.state().arm.motion_ready,true);
 }
});

test('a frozen measured sample expires even while status and game messages keep arriving',async()=>{
 const b=await bridge('green',2200);assert((await b.command()).ok);
 for(let i=0;i<16;i++)await b.advance(100,{feedback:false});
 assert.equal(b.state().arm.session,null);assert.equal(b.state().arm.motion_ready,false);
 assert(b.calls.some(x=>x.path==='/api/stop'));assert(b.calls.some(x=>x.path==='/api/disconnect'));
});

test('repeated cached status and arm timestamps cannot renew feedback indefinitely',async()=>{
 const b=await bridge();await b.publish({feedback_observed_at:b.clock.server});assert((await b.command()).ok);
 for(let i=0;i<16;i++){
  b.c.mobileGameAt=b.clock.now+100;
  await b.advance(100,{game:false,feedback:false});
 }
 assert.equal(b.state().arm.session,null);assert.equal(b.state().arm.motion_ready,false);
});

test('already aged feedback retains its original expiry across cached re-delivery',async()=>{
 const b=await bridge();await b.publish({last_feedback:b.clock.server-1.2,feedback_observed_at:b.clock.server});assert((await b.command()).ok);
 for(let i=0;i<4;i++){
  b.c.mobileGameAt=b.clock.now+100;
  await b.advance(100,{game:false,feedback:false});
 }
 assert.equal(b.state().arm.session,null);assert.equal(b.state().arm.motion_ready,false);
});

test('missing, stale, future, or invalid time evidence fails closed',async()=>{
 for(const mutate of [
  b=>{b.c.mobileGame=null;},b=>b.publish({feedback_observed_at:undefined}),
  b=>b.publish({feedback_observed_at:NaN}),b=>b.publish({feedback_observed_at:'invalid'}),b=>{b.c.mobileGameAt=NaN;},
  b=>{b.c.mobileGameAt=b.clock.now+1;},b=>{b.c.mobileGameAt=b.clock.now-2100;},
  b=>b.publish({last_feedback:b.clock.server-1.6}),b=>b.publish({last_feedback:b.clock.server+1}),
  b=>b.publish({last_feedback:NaN}),b=>b.publish({last_feedback:'1792588055'}),
  b=>b.publish({feedback_ok:false}),b=>b.publish({motion_ready:false}),b=>b.publish({enabled:false})
 ]){
  const b=await bridge();await mutate(b);const reply=await b.command();
  assert.equal(reply.ok,false);assert.equal(reply.arm.session,null);
 }
});

test('independent game watchdog still stops controls when game delivery stops',async()=>{
 const b=await bridge();assert((await b.command()).ok);
 for(let i=0;i<21;i++)await b.advance(100,{game:false});
 assert.equal(b.state().arm.session,null);
 assert(b.posted.some(p=>p.type==='diagnostic'&&p.event==='game_not_ready'));
});

test('unlock, disconnection, and a new motion epoch still revoke the current session',async()=>{
 for(const fields of [{robot_mode:6,motion_ready:false},{connected:false},{motion_epoch:2}]){
  const b=await bridge('purple',-2200);assert((await b.command()).ok);await b.publish(fields);
  assert.equal(b.state().arm.session,null);assert(b.calls.some(x=>x.path==='/api/stop'));
 }
});


test('both teams stay connected when game projections trail fresh robot status',async()=>{
 for(const team of ['green','purple']){
  const b=await bridge(team,2200);const session=(await b.command()).arm.session;
  for(const lag of [350,800,1200]){
   b.clock.now+=100;b.clock.server+=.1;
   b.c.mobileGame.server_time=b.clock.server-lag/1000;b.c.mobileGameAt=b.clock.now;
   await b.publish({last_feedback:b.clock.server-.02});
   assert.equal(b.state().arm.session,session);
   assert(Math.abs(b.state().diagnostics.feedback_age_ms-20)<.01);
   assert(b.state().diagnostics.feedback_game_delta_ms< -250);
  }
 }
});

test('slow status delivery counts toward the 1.5 second feedback lifetime',async()=>{
 const b=await bridge();assert((await b.command()).ok);
 b.clock.requestMs=1481;await b.publish({last_feedback:b.clock.server-.02});
 assert.equal(b.state().arm.session,null);
 assert(b.posted.some(p=>p.type==='diagnostic'&&p.event==='feedback_stale'));
});

test('a status with no measured request receipt cannot grant fresh feedback',async()=>{
 const b=await bridge();assert((await b.command()).ok);
 b.c.applyStatus({connected:true,enabled:true,feedback_ok:true,motion_ready:true,control_session:'relay-1',motion_epoch:1,
  last_feedback:b.clock.server,feedback_observed_at:b.clock.server,pose:[300,100,50,9],joints:[0,20,30,9]});
 assert.equal(b.state().arm.session,null);
});
