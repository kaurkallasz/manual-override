/* Pure JS checks; no browser, relay, or hardware connection. */
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const html=fs.readFileSync('shared/robot_controls/controller.html','utf8');
for(const [,script] of html.matchAll(/<script>([\s\S]*?)<\/script>/g))new vm.Script(script);
let now=1000,calls=[],elements=new Map(),response={};
const node=id=>{if(!elements.has(id))elements.set(id,{options:[1,2,3,4].map(value=>({value:String(value)}))});return elements.get(id);};
const ctx={TEAM:'green',URLSearchParams,AbortSignal,AbortController,setTimeout,clearTimeout,performance:{now:()=>now},
 LTZ:true,location:{search:'?ltz=1&mobile=1'},document:{hidden:false,body:{classList:{toggle(){}}},querySelector:()=>node('heading')},
 gid:node,pauseUserMoves(){},autoPpxAbort:false,autoPpxRunning:false,autoPpxClickOverride:false,armConnectBusy:false,
 BASE:'/s/green/p/cartesian-xyz-test/',log(){},applyLtxConfig:value=>{ctx.layout=value;},
 fetch:async(url,opts)=>{calls.push({url,opts});return {ok:true,json:async()=>url.includes('mobile-ltz-api')?response:{ok:true}};}};
vm.createContext(ctx);
vm.runInContext(html.slice(html.indexOf('const MOBILE_LTZ ='),html.indexOf('function applyLtzProgress')),ctx);
vm.runInContext(html.slice(html.indexOf('async function api('),html.indexOf('function report(')),ctx);
const run=code=>vm.runInContext(code,ctx);
(async()=>{
 assert.equal((await run("api('/api/move',{x:1})")).ok,false);assert.equal(calls.length,0);
 response={contract:'photon.game',version:2,status:'ready',virtual_play:false,phase:'setup',virtual_test_control:1};
 await run('pollMobileGame()');assert(run('mobileRobotReady()'));assert(ctx.layout.visibility.joint_angles);
 calls=[];assert.equal((await run("api('/api/move',{x:1})")).ok,false);assert.equal(calls.length,0,'XYZ locked at tier 1');
 await run("api('/api/joint-move',{joints:[1,2,3,4],cal2_guard:{token:'test'}})");
 assert.equal(calls[0].url,'/s/green/p/cartesian-xyz-test/api/joint-move');
 assert.equal(JSON.parse(calls[0].opts.body).ltz_action,'joint');assert.equal(JSON.parse(calls[0].opts.body).cal2_guard.token,'test');
 response.virtual_test_control=4;run('mobileControlChoice=4');await run('pollMobileGame()');assert(ctx.layout.visibility.auto_pp_x);
 response.journey={phase:'ready'};await run('pollMobileGame()');assert(run('mobileRobotReady()'),'GM test unlocks remain usable during an ordinary ready transition');
 response.journey={phase:'calibration',active_side:'purple'};await run('pollMobileGame()');assert(!run('mobileRobotReady()'),'Test unlocks cannot override exclusive calibration');
 response.journey=null;await run('pollMobileGame()');
 calls=[];await run("api('/api/move',{x:1,y:2,z:3,r:4})");assert.equal(JSON.parse(calls[0].opts.body).ltz_action,'xyz');
 run('autoPpxRunning=true');await run("api('/api/move',{x:1})");assert.equal(JSON.parse(calls[1].opts.body).ltz_action,'cue');run('autoPpxRunning=false');
 response.paused=true;calls=[];await run('pollMobileGame()');assert(!run('mobileRobotReady()'));
 assert(calls.some(c=>c.url.endsWith('/api/stop')));assert(calls.some(c=>c.url.endsWith('/api/pump')&&JSON.parse(c.opts.body).mode==='off'));
 calls=[];assert.equal((await run("api('/api/pump',{mode:'suck'})")).ok,false);assert.equal(calls.length,0);
 response.paused=false;await run('pollMobileGame()');now+=2100;assert(!run('mobileRobotReady()'));
 calls=[];assert.equal((await run("api('/api/enable',{})")).ok,false);assert.equal(calls.length,0);
 await run("api('/api/stop',{})");assert.equal(calls.length,1,'Stop stays available');
 response.virtual_play=true;await run('pollMobileGame()');assert(!run('mobileRobotReady()'));
 response.virtual_play=false;await run('pollMobileGame()');run('mobileViewActive=false');assert(!run('mobileRobotReady()'));
 console.log('PASS: physical mode, freshness, pause, visibility, tiers, guarded relay routing and stop');
})().catch(e=>{console.error(e);process.exitCode=1;});
