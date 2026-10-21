/* Offline/reload retry and bounded diagnostics, with no browser or robot I/O. */
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),crypto=require('node:crypto').webcrypto;
const source=fs.readFileSync('shared/mobile_ltz/connection-log.js','utf8');
const store={};
Object.defineProperties(store,{getItem:{value:key=>store[key]??null},setItem:{value:(key,value)=>{store[key]=value;}},removeItem:{value:key=>{delete store[key];}}});
let requests=[],reachable=false,at=100000;
function browser(team='green'){
 const timers=new Map();let next=0;
 const ctx={crypto,AbortController,URLSearchParams,localStorage:store,navigator:{onLine:true},document:{hidden:false,hasFocus:()=>true},
  Date:{now:()=>at},window:{addEventListener(){}},setTimeout:fn=>{timers.set(++next,fn);return next;},clearTimeout:id=>timers.delete(id),
  fetch:async(url,options)=>{requests.push({url,options});if(!reachable)throw Error('offline');return {ok:true,status:200,json:async()=>({ok:true})};}};
 vm.createContext(ctx);vm.runInContext(source,ctx);
 const log=vm.runInContext(`new MobileConnectionLog({team:'${team}',url:'/diagnostics?side=${team}',context:()=>({game_age_ms:2600,had_session:true})})`,ctx);
 return {log,timers};
}
(async()=>{
 const {log}=browser();
 log.record('player','suspend','Live game timed out.');
 assert.equal(requests.length,0,'Recording must leave Stop free to run before network/storage work');
 log.record('player','suspend','Live game timed out.');assert.equal(log.queue.length,1,'Repeated watchdog messages are deduplicated');
 await log.flush();assert.equal(log.queue.length,1,'Outage retains the evidence');
 const first=JSON.parse(requests[0].options.body);assert.equal(first.context.game_age_ms,2600);assert(first.context.had_session);
 const replacement=browser().log;assert.equal(replacement.queue.length,1,'Refresh restores the pending event');
 assert.equal(browser('purple').log.queue.length,0,'Team queues remain separate');
 reachable=true;await replacement.flush();assert.equal(replacement.queue.length,0);
 assert.equal(JSON.parse(requests.at(-1).options.body).id,first.id,'Retries keep a deduplicatable event id');
 assert.equal(requests.at(-1).options.keepalive,true);
 assert.equal(browser().log.queue.length,0,'Acknowledged events do not replay after refresh');
 replacement.context=()=>({feedback_age_ms:475,had_session:true});
 replacement.record('bridge','feedback_stale','Invalid timestamp',{feedback_age_ms:null,feedback_game_delta_ms:-350});
 assert.equal(replacement.queue.at(-1).context.feedback_age_ms,null,'Unavailable age must not inherit an old valid measurement');
 assert.equal(replacement.queue.at(-1).context.feedback_game_delta_ms,-350);
 replacement.record('bridge','status_read_failed','token='+'a'.repeat(32)+' https://test/?auth=secret',{robot_error:'cookie=private'});
 replacement.persist();const saved=JSON.stringify(store);assert(!saved.includes('auth=secret'));assert(!saved.includes('cookie=private'));assert(!saved.includes('a'.repeat(32)));
 for(let i=0;i<100;i++){at+=4000;replacement.record('bridge','game_not_ready','sample '+i);}
 assert.equal(replacement.queue.length,64,'An offline tab cannot grow indefinitely');
 const broken=browser().log;broken.context=()=>{throw Error('bad context');};assert.doesNotThrow(()=>broken.record('player','stop'));
 console.log('mobile connection log: offline retry, refresh recovery, team isolation, redaction and bounds passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
