/* Run: node --test tests/laser_tag_y_commands.test.js */
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const page=fs.readFileSync(path.join(__dirname,'../sandboxes/gamemaster/prototypes/laser-tag-y/index.html'),'utf8');
const between=(a,b)=>page.slice(page.indexOf(a),page.indexOf(b,page.indexOf(a)));
const source=between('let calibrationBusy=','// Display-only pixel branch.')
 +between("let startError=",'function paintHud()')
 +between('async function startGame()', 'async function boot()');
const flush=async()=>{for(let i=0;i<20;i++)await Promise.resolve()};
const setupState={contract:'photon.game',status:'ready',phase:'setup',virtual_play:false,journey:{phase:'lobby'},inputs:{board:{status:'ready'}}};
function setup(){
 const nodes=new Map(),streams=[],requests=[],timers=new Map(),logs=[],paints=[];let timerId=0;
 const $=id=>{if(!nodes.has(id))nodes.set(id,{checked:false,setAttribute(){}});return nodes.get(id)};
 const c=vm.createContext({$,SELF:'/s/gamemaster/p/laser-tag-y',AbortController,
  ui:{events:null,booted:true,state:{...setupState},view:{setFeedConnected(){}}},
  document:{hidden:false},dataFlow:{connection(){}},
  operatorCamera:{frame(){},disconnect(){},suspend(){},resume(){}},
  arucoMonitor:{update(){},disconnect(){}},savedCalibrations:{camera(){}},syncAruco(){},
  TowerDefenceView:{presentation:{snapshotReceiver(fn){return {full:fn,update:fn}}}},
  EventSource:class{constructor(url){this.url=url;this.handlers={};streams.push(this)}close(){this.closed=true}addEventListener(k,fn){this.handlers[k]=fn}},
  setTimeout(fn,delay){timers.set(++timerId,{fn,delay});return timerId},clearTimeout(id){timers.delete(id)},
  log:t=>logs.push(t),
  fetch(url,options){
   assert(streams.every(s=>s.closed),'Free Y’s streaming connection before HTTP requests');
   return new Promise((resolve,reject)=>{
    requests.push({url,options,resolve,reject});
    options.signal.addEventListener('abort',()=>reject(Error('aborted')),{once:true});
   });
  },
 });
 c.applyState=value=>{c.ui.state=value};c.paintHud=()=>paints.push(vm.runInContext('({startBusy,startError})',c));
 vm.runInContext(source,c);c.connectGameEvents();
 return {c,$,streams,requests,timers,logs,paints,run:s=>vm.runInContext(s,c),
  respond(i,value,ok=true){requests[i].resolve({ok,status:ok?200:400,text:async()=>JSON.stringify(value)})},
  expire(){[...timers.values()].find(t=>t.delay===15000).fn()}};
}
test('Start releases the stream, blocks duplicate clicks, and waits for authoritative running state',async()=>{
 const h=setup(),pending=h.c.startGame();
 assert.equal(h.requests.length,1);assert.equal(JSON.parse(h.requests[0].options.body).action,'start');
 assert.equal(h.paints[0].startBusy,true);assert.equal(h.c.ui.state.phase,'setup');
 await h.c.startGame();assert.equal(h.requests.length,1);
 h.c.connectGameEvents();h.c.syncLiveVisibility();assert.equal(h.streams.length,1);
 h.respond(0,{output:{...setupState,phase:'running'}});await pending;
 assert.equal(h.c.ui.state.phase,'running');assert.equal(h.paints.at(-1).startBusy,false);
 assert.equal(h.logs.at(-1),'Defense started.');assert.equal(h.streams.filter(s=>!s.closed).length,1);
 assert.equal(h.timers.size,0);
});
test('backend rejection is displayed and never claims the game started',async()=>{
 const h=setup(),pending=h.c.startGame();h.respond(0,{error:'Photon Board observation is stale'},false);await pending;
 assert.match(h.paints.at(-1).startError,/observation is stale/);assert.equal(h.c.ui.state.phase,'setup');
 assert(!h.logs.includes('Defense started.'));assert.equal(h.streams.filter(s=>!s.closed).length,1);
});
test('timed-out Start recovers the live stream without automatically retrying the command',async()=>{
 const h=setup(),pending=h.c.startGame();h.expire();await pending;
 assert.match(h.paints.at(-1).startError,/timed out.*live game state/);
 assert.equal(h.requests.length,1);assert.equal(h.paints.at(-1).startBusy,false);assert.equal(h.timers.size,0);
 assert.equal(h.streams.filter(s=>!s.closed).length,1);
});
test('unlocks hold a free connection through follow-up snapshot and full body parsing',async()=>{
 const h=setup(),pending=h.c.command({action:'virtual_test_loadout',control:4,levels:null});
 h.respond(0,{output:{contract:'photon.game.journey'}});await flush();assert.equal(h.requests.length,2);
 assert.equal(h.requests[0].options.signal,h.requests[1].options.signal);
 let finish;h.requests[1].resolve({ok:true,text:()=>new Promise(resolve=>{finish=resolve})});await flush();
 h.c.syncLiveVisibility();assert.equal(h.streams.filter(s=>!s.closed).length,0);
 finish(JSON.stringify(setupState));await pending;assert.equal(h.streams.filter(s=>!s.closed).length,1);
});
test('concurrent reads reserve the connection until both finish and do not reconnect hidden/unloaded pages',async()=>{
 const h=setup(),one=h.c.json('/api/state'),two=h.c.json('/api/calibrations');
 h.respond(0,setupState);await one;assert.equal(h.streams.filter(s=>!s.closed).length,0);
 h.run('pageActive=false');h.respond(1,{entries:[]});await two;assert.equal(h.streams.filter(s=>!s.closed).length,0);
 h.run('pageActive=true');h.c.document.hidden=true;h.c.connectGameEvents();assert.equal(h.streams.length,1);
 h.c.document.hidden=false;h.c.connectGameEvents();assert.equal(h.streams.length,2);
});
