/* Run: node --test tests/calibration_commands.test.js
   Exercise Y's real command/camera/SSE functions without hardware or a server. */
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const page=fs.readFileSync(path.join(__dirname,'../sandboxes/gamemaster/prototypes/laser-tag-y/index.html'),'utf8');
const between=(start,end)=>page.slice(page.indexOf(start),page.indexOf(end,page.indexOf(start)));
const source=between('let calibrationBusy=', '// Display-only pixel branch.')
  +between('function createOperatorCamera(', '// This monitor')
  +between('function disconnectGameEvents()', 'async function boot()');
const flush=async()=>{for(let i=0;i<12;i++)await Promise.resolve()};
function setup(){
  const nodes=new Map(),timers=new Map(),requests=[],sources=[],logs=[],applied=[];
  let timerId=0,receivers=0,cameraOpen=false;
  const $=id=>{if(!nodes.has(id))nodes.set(id,{setAttribute(k,v){this[k]=v}});return nodes.get(id)};
  const image={hidden:true,removeAttribute(){cameraOpen=false},set src(value){cameraOpen=!!value}};
  const context=vm.createContext({$,SELF:'/s/gamemaster/p/laser-tag-y',AbortController,performance:{now:()=>0},
    setTimeout(fn,delay){const id=++timerId;timers.set(id,{fn,delay});return id},clearTimeout(id){timers.delete(id)},
    log:message=>logs.push(message),
    document:{hidden:false},ui:{booted:true,state:{status:'ready',phase:'setup',journey:{phase:'calibration',active_side:'green'},inputs:{board:{status:'ready',upstream:{source:'camera'}}}},view:{setFeedConnected(){}},events:null},
    dataFlow:{connection(){}},arucoMonitor:{update(){},disconnect(){}},savedCalibrations:{camera(){}},syncAruco(){},
    TowerDefenceView:{presentation:{snapshotReceiver(apply){receivers++;return {full:apply,update:apply}}}},
    EventSource:class{
      constructor(url){this.url=url;this.closed=false;this.handlers={};sources.push(this)}
      addEventListener(type,fn){this.handlers[type]=fn}
      close(){this.closed=true}
    },
    fetch(url,options){
      // Four other live feeds plus Y's camera/SSE fill the browser's six slots.
      assert.equal(cameraOpen,false,'Release camera before requesting a screen change');
      assert(sources.every(s=>s.closed),'Release SSE before requesting a screen change');
      return new Promise((resolve,reject)=>{
        const request={url,options,resolve,reject};requests.push(request);
        options.signal.addEventListener('abort',()=>reject(Error('aborted')),{once:true});
      });
    },
  });
  context.applyState=state=>{context.ui.state=state;applied.push(state);context.operatorCamera.update(state)};
  vm.runInContext(source,context);
  context.operatorCamera=context.createOperatorCamera({stage:{classList:{toggle(){}}},image,message:{},retry:{},fps:{},url:'/camera'});
  context.operatorCamera.update(context.ui.state);context.connectGameEvents();
  const showFrame=()=>{sources.filter(s=>!s.closed).at(-1).handlers.camera({data:JSON.stringify({contract:'laser-tag-y.camera',version:1,status:'ready',frame_at:Date.now()/1000,width:1280,height:720,image:'data:image/jpeg;base64,ZmFrZQ=='})});image.onload()};
  showFrame();
  const respond=(request,value,ok=true)=>request.resolve({ok,status:ok?200:503,text:async()=>JSON.stringify(value)});
  const expire=()=>{const timer=[...timers.values()].find(t=>t.delay===15000);assert(timer,'Commands have a bounded deadline');timer.fn()};
  const buttons=()=>['cancelCalibration','calibrateGreen','calibratePurple','calibrateBoth','resumeCalibration'].map($);
  return {context,$,showFrame,requests,sources,logs,applied,timers,respond,expire,buttons,cameraOpen:()=>cameraOpen,receivers:()=>receivers};
}
const lobby={contract:'photon.game',status:'ready',phase:'setup',journey:{phase:'lobby'},inputs:{board:{status:'ready',upstream:{source:'camera'}}}};

test('screen exit frees connections through command and snapshot, then resumes one fresh stream',async()=>{
  const h=setup(),c=h.context,old=h.sources[0];
  const pending=c.calibrationCommand({action:'show_game'});
  assert(h.buttons().every(b=>b.disabled));assert.equal(h.$('calibrationStatus').textContent,'Changing screen…');
  assert.equal(c.ui.state.journey.phase,'calibration','Do not invent a successful exit');
  await c.calibrationCommand({action:'calibration_test',side:'purple'});
  assert.equal(h.requests.length,1,'Duplicate clicks cannot send another command');
  c.operatorCamera.check();c.operatorCamera.update(c.ui.state);
  assert.equal(h.cameraOpen(),false,'Watchdog and snapshots must preserve the free slot');
  h.respond(h.requests[0],{output:{contract:'photon.game.journey',phase:'lobby'}});await flush();
  assert.equal(h.requests.length,2);assert(h.requests[1].url.endsWith('/api/state'));
  assert.equal(h.requests[0].options.signal,h.requests[1].options.signal,'The same deadline covers both requests');
  assert(h.buttons().every(b=>b.disabled));assert.equal(h.cameraOpen(),false);
  h.respond(h.requests[1],lobby);await pending;
  assert.equal(c.ui.state.journey.phase,'lobby');assert(h.buttons().every(b=>!b.disabled));
  assert.equal(h.timers.size,0);assert.equal(h.cameraOpen(),false);h.showFrame();assert.equal(h.cameraOpen(),true);
  assert.equal(h.sources.filter(s=>!s.closed).length,1);assert.equal(h.receivers(),2);
  const before=h.applied.length;
  old.onmessage({data:JSON.stringify({journey:{phase:'calibration'}})});
  old.handlers.update({data:'{}'});old.onerror();
  assert.equal(h.applied.length,before,'Late events from the closed stream cannot undo the exit');
  c.connectGameEvents();assert.equal(h.sources.length,2,'Reconnect is idempotent');
});

test('server errors restore controls and streams without claiming calibration exited',async()=>{
  const h=setup(),pending=h.context.calibrationCommand({action:'show_game'});
  h.respond(h.requests[0],{error:'Display reservation unavailable'},false);await pending;
  assert(h.buttons().every(b=>!b.disabled));assert.equal(h.cameraOpen(),false);h.showFrame();assert.equal(h.cameraOpen(),true);
  assert.equal(h.context.ui.state.journey.phase,'calibration');
  assert.equal(h.$('calibrationStatus').textContent,'Display reservation unavailable');
  assert.equal(h.sources.filter(s=>!s.closed).length,1);assert.equal(h.timers.size,0);
});

for(const stage of ['command','snapshot','body'])test(`a stalled ${stage} times out and permits another screen selection`,async()=>{
  const h=setup(),pending=h.context.calibrationCommand({action:'show_game'});
  if(stage!=='command'){
    h.respond(h.requests[0],{output:{contract:'photon.game.journey'}});await flush();
    if(stage==='body'){
      const request=h.requests[1];
      request.resolve({ok:true,text:()=>new Promise((_,reject)=>request.options.signal.addEventListener('abort',()=>reject(Error('aborted')),{once:true}))});
      await flush();
    }
  }
  h.expire();await pending;
  assert(h.buttons().every(b=>!b.disabled));assert.match(h.$('calibrationStatus').textContent,/timed out/);
  assert.equal(h.context.ui.state.journey.phase,'calibration');assert.equal(h.timers.size,0);
  assert.equal(h.sources.filter(s=>!s.closed).length,1);
  const before=h.requests.length,next=h.context.calibrationCommand({action:'calibration_test',side:'purple'});
  assert.equal(h.requests.length,before+1,'Recovery needs no page refresh or automatic command retry');
  h.respond(h.requests[before],{output:lobby});await next;
  assert(h.buttons().every(b=>!b.disabled));assert.equal(h.context.ui.state.journey.phase,'lobby');
});


test('hidden views release the one event connection and wait for fresh frames on return',()=>{
  const h=setup(),c=h.context,old=h.sources[0];
  assert.match(old.url,/markers=1&preview=1/);
  c.document.hidden=true;c.syncLiveVisibility();
  assert(old.closed);assert.equal(h.cameraOpen(),false);
  c.connectGameEvents();assert.equal(h.sources.length,1);
  old.handlers.camera({data:'{}'});assert.equal(h.cameraOpen(),false);
  c.document.hidden=false;c.syncLiveVisibility();c.syncLiveVisibility();
  assert.equal(h.sources.length,2);assert.equal(h.cameraOpen(),false);
  h.sources[1].onmessage({data:JSON.stringify(lobby)});h.showFrame();
  assert.equal(h.cameraOpen(),true);
});
