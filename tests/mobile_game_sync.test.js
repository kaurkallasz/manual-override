'use strict';
const assert=require('node:assert/strict');
const GameState=require('../sandboxes/green/prototypes/mobile-ltz/live-game.js');
const level={width:1696,height:960,paths:[],sockets:[]};
const setup={status:'ready',virtual_play:true,phase:'setup',run_id:null,level_revision:1,level,server_time:1};
const running={...setup,phase:'running',run_id:'run-1',server_time:2};

(async()=>{
  const seen=[];let loads=0;
  const receiver=new GameState({apply:s=>seen.push(s),load:async()=>{loads++;return running;}});
  receiver.receive(setup);
  receiver.receive({phase:'running',run_id:'run-1',server_time:2},true);
  assert.equal(seen.at(-1).phase,'running');assert.equal(seen.at(-1).level,level);
  assert.equal(loads,0,'starting the shared run needs no player command or extra fetch');
  receiver.receive({status:'ready',virtual_play:true,phase:'running',run_id:'run-1',level_revision:1,server_time:3});
  assert.equal(seen.at(-1).level,level,'a partial plain message cannot discard the scene');

  const presentation={contract:'photon.level.assets',version:1,status:'ready',base:'/art',revision:'one',assets:{}};
  receiver.receive({...running,presentation,server_time:4});
  for(let i=5;i<30;i++){
    // Reproduce the hosted relay losing the SSE event label.
    receiver.receive({contract:'hub.live',version:1,kind:'update',state:{status:'ready',run_id:'run-1',level_revision:1,server_time:i,enemies:[{id:i}]}},false);
    assert.equal(receiver.value.level,level);assert.equal(receiver.value.presentation,presentation);
    assert.equal(receiver.value.enemies[0].id,i);
  }
  receiver.receive({status:'ready',server_time:30,enemies:[]},false);
  assert.equal(receiver.value.presentation,presentation,'an unidentified plain delta cannot erase artwork');
  receiver.receive({...running,server_time:3});
  assert.equal(receiver.value.server_time,29,'a buffered old snapshot cannot rewind the game');
  assert.throws(()=>receiver.receive({contract:'hub.live',version:2,kind:'update',state:running}),/Invalid live message/);

  let finish;const errors=[];
  const late=new GameState({apply:s=>seen.push(s),load:()=>{loads++;return new Promise(resolve=>finish=resolve);},error:e=>errors.push(e)});
  late.receive({...running,level:undefined});
  const recovery=late.recover();await Promise.resolve();
  late.receive({wave:2,server_time:4},true);
  finish(running);await recovery;
  assert.equal(late.value.level,level);assert.equal(late.value.wave,2,'recovery must preserve newer gameplay');
  assert.equal(errors.length,0);

  const artRecovery=new GameState({apply:()=>{},load:async()=>({...running,presentation,server_time:1})});
  const newerArt={...presentation,revision:'two'};
  artRecovery.receive({...running,presentation:newerArt,server_time:5});await artRecovery.recover();
  assert.equal(artRecovery.value.presentation,newerArt,'an older recovery cannot restore obsolete artwork');

  const changed=new GameState({apply:()=>{},load:()=>new Promise(resolve=>finish=resolve)});
  changed.receive({...running,level:undefined});const oldRecovery=changed.recover();await Promise.resolve();
  const next={...running,run_id:'run-2',level_revision:2,level:{...level,width:2000},server_time:5};
  changed.receive(next);finish(running);await oldRecovery;
  assert.equal(changed.value.run_id,'run-2');assert.equal(changed.value.level.width,2000,'late recovery cannot restore the old map');

  const offline=new GameState({apply:()=>{},load:async()=>{throw Error('offline');},error:e=>errors.push(e)});
  offline.receive({...running,level:null});await offline.recover();
  assert.equal(errors.at(-1).message,'offline');assert.ok(offline.retryAt>Date.now());
  console.log('Run start, scene retention, late join, stale recovery and retry checks passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
