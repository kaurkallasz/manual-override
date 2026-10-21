// Start starter_defenses_fixture.py. These checks never contact the live hub.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require('playwright');
const origin='http://127.0.0.1:'+fs.readFileSync('/tmp/starter-defenses-port','utf8');
const output=path.resolve('output/atom-homes-2026-10-19');fs.mkdirSync(output,{recursive:true});
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const errors=[];const results={};
 try{
  const screen=await browser.newPage({viewport:{width:1920,height:1080}});
  screen.on('pageerror',e=>errors.push(e.message));
  await screen.addInitScript(()=>{
   let api;Object.defineProperty(window,'TowerDefenceView',{get:()=>api,set(value){api=value;const create=value.create;
    value.create=options=>{const view=create({...options,onAssetStatus:s=>{window.assetStatus=s;options.onAssetStatus?.(s);}});
     const apply=view.applyState;view.applyState=s=>{window.gameState=s;return apply(s)};window.fixtureView=view;return view;};}});
  });
  await screen.goto(origin+'/s/gamemaster/p/laser-tag-y/screen');
  await screen.waitForFunction(()=>window.gameState?.status==='ready'&&assetStatus?.loaded>0&&assetStatus.pending===0);
  assert.equal(await screen.evaluate(()=>assetStatus.failed),0);
  for(const level of [1,3,4]){
   const response=await screen.request.post(origin+'/__test/starters',{data:{level}});assert.ok(response.ok());
   await screen.waitForFunction(l=>gameState.event_game?.level===l,level);
   const visible=await screen.evaluate(()=>{
    const labels=[],fill=CanvasRenderingContext2D.prototype.fillText;
    CanvasRenderingContext2D.prototype.fillText=function(text,...args){if(['100','101','102','103'].includes(String(text)))labels.push(String(text));return fill.call(this,text,...args)};
    fixtureView.renderGame(performance.now());CanvasRenderingContext2D.prototype.fillText=fill;
    return {labels:[...new Set(labels)].sort(),count:gameState.starter_turrets.length,
     ids:gameState.home_platforms.map(h=>h.atom_tag_id).sort(),tiers:gameState.starter_turrets.map(t=>t.upgrade_level),
     companions:gameState.companions.length,ring:gameState.core_sequence.ring_candidate_count};
   });
   const ids=level===4?[100,101,102,103]:[100,102];
   assert.deepEqual(visible.ids,ids);assert.deepEqual(visible.labels,ids.map(String));
   assert.equal(visible.count,ids.length);assert.equal(visible.companions,0);assert.equal(visible.ring,0);
   assert.ok(visible.tiers.every(t=>t===level));results['L'+level]=visible;
   await screen.screenshot({path:path.join(output,`screen-l${level}.png`)});
  }
  const operator=await browser.newPage({viewport:{width:1800,height:1200}});
  operator.on('pageerror',e=>errors.push(e.message));
  await operator.goto(origin+'/s/gamemaster/p/laser-tag-y/game');
  await operator.waitForFunction(()=>ui.state?.starter_turrets?.length===4&&ui.view?.levelReady);
  await operator.locator('#gameCanvas').scrollIntoViewIfNeeded();
  const t=await operator.evaluate(()=>ui.state.starter_turrets[0]);
  const bounds=await operator.locator('#gameCanvas').boundingBox();
  await operator.mouse.click(bounds.x+t.x*bounds.width/1696,bounds.y+t.y*bounds.height/960);
  await operator.waitForFunction(sid=>ui.selectedTower===sid,t.socket_id);
  assert.match(await operator.locator('#aimTitle').textContent(),/Starter/);
  await operator.evaluate(async()=>{setAimDraft(175,.7,false);await saveAim();});
  await operator.waitForFunction(()=>Math.abs(ui.state.starter_turrets[0].targeting.angle_degrees-175)<.01);
  await operator.locator('#stage').screenshot({path:path.join(output,'operator-l4.png')});
  const before=await operator.evaluate(()=>ui.state.starter_turrets[0].aim_instance);
  await operator.request.post(origin+'/__test/destroy-starter');
  await operator.waitForFunction(()=>ui.state.starter_turrets[0].destroyed);
  const rejected=await operator.request.post(origin+'/s/gamemaster/p/photon-game/api/command',{
   data:{action:'operator_atom',socket_id:t.socket_id,atom_tag_id:100}});
  assert.equal(rejected.status(),400);
  await screen.reload();await screen.waitForFunction(()=>gameState?.starter_turrets?.[0]?.destroyed&&assetStatus?.pending===0);
  assert.equal(await screen.evaluate(()=>gameState.starter_turrets[0].aim_instance),before);
  assert.equal(await screen.evaluate(()=>gameState.starter_turrets[0].hp),0);
  await screen.screenshot({path:path.join(output,'screen-destroyed.png')});
  await screen.request.post(origin+'/__test/starters',{data:{level:4,full_board:true}});
  await screen.waitForFunction(()=>gameState.companions?.length===12&&gameState.towers?.length===16);
  assert.equal(await screen.evaluate(()=>gameState.starter_turrets.length),4);
  await screen.screenshot({path:path.join(output,'screen-full-l4.png')});
  await screen.setViewportSize({width:1366,height:768});
  await screen.screenshot({path:path.join(output,'screen-full-l4-1366.png')});
  results.destroyedSurvivesReload=true;results.totalL4Units=32;results.errors=errors;
  assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(output,'browser-results.json'),JSON.stringify(results,null,2)+'\n');
  console.log(JSON.stringify(results));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
