// Run clean_reset_fixture.py first. All hardware and saved data are isolated.
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
const path=require('node:path'),fs=require('node:fs');
const origin='http://qr-game.test:8164';
const output=path.resolve(__dirname,'../output/player-join-2026-10-21');
fs.mkdirSync(output,{recursive:true});
(async()=>{
  const browser=await chromium.launch({headless:true,
    executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    args:['--host-resolver-rules=MAP qr-game.test 127.0.0.1','--no-proxy-server']});
  try{
    const gmContext=await browser.newContext({viewport:{width:1400,height:1000}}),gm=await gmContext.newPage();
    const errors=[];gm.on('pageerror',e=>errors.push(e.message));
    await gm.goto(origin+'/s/gamemaster/p/laser-tag-y/game');
    await gm.locator('[name=password]').fill('fixture-gamemaster');await gm.locator('button[type=submit]').click();
    await gm.waitForSelector('.player-join-card img');
    await gm.waitForFunction(()=>!document.querySelector('#cleanResetPlayers').disabled);
    const getLinks=async()=> gm.evaluate(async()=> (await (await fetch('/s/gamemaster/api/player-join')).json()).links);
    const oldLinks=await getLinks(),players=[];
    for(const team of ['green','green','purple']){
      const context=await browser.newContext({viewport:{width:430,height:900}}),page=await context.newPage();
      page.on('pageerror',e=>errors.push(e.message));
      await page.goto(oldLinks.find(l=>l.team===team).url);
      await page.waitForURL(origin+`/s/${team}/p/mobile-ltz/`);
      players.push({context,page,team});
    }
    await gm.waitForFunction(()=>document.querySelectorAll('#playerConnectionRows tr[data-ended=false]').length===3);
    assert.match(await gm.locator('#playerConnectionRows').innerText(),/green pilot/);
    assert.match(await gm.locator('#playerConnectionRows').innerText(),/purple pilot/);
    assert.equal(await gm.locator('#playerJoin button').filter({hasText:/^Kick$/}).count(),0);
    await gm.locator('#playerJoin').screenshot({path:path.join(output,'connections-before-clean-reset.png')});
    // Ordinary regeneration keeps all sessions connected.
    await gm.locator('#regeneratePlayerCodes').click();
    await gm.waitForFunction(()=>!document.querySelector('#regeneratePlayerCodes').disabled);
    for(const p of players)assert.equal(await p.page.evaluate(async team=>(await fetch(`/s/${team}/api/meta`)).status,p.team),200);
    // A stop failure must hide all codes, revoke everyone and survive a reload.
    await gm.evaluate(()=>fetch('/__test/stop-failure',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled:true})}));
    await gm.locator('#cleanResetPlayers').click();
    await gm.waitForFunction(()=>document.querySelector('#cleanResetPlayers').textContent==='Retry clean reset');
    assert(await gm.locator('#playerJoinCards').isHidden());
    for(const p of players)await p.page.waitForURL(/\/login\?ended=1/, {timeout:12000});
    await gm.reload();
    await gm.waitForFunction(()=>document.querySelector('#cleanResetPlayers').textContent==='Retry clean reset'&&!document.querySelector('#cleanResetPlayers').disabled);
    assert(await gm.locator('#regeneratePlayerCodes').isDisabled());
    await gm.locator('#playerJoin').screenshot({path:path.join(output,'clean-reset-stop-failure.png')});
    await gm.evaluate(()=>fetch('/__test/stop-failure',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled:false})}));
    await gm.locator('#cleanResetPlayers').click();
    await gm.waitForFunction(()=>document.querySelector('#cleanResetPlayers').textContent==='Clean reset'&&!document.querySelector('#playerJoinCards').hidden);
    const fresh=await getLinks();
    for(const link of oldLinks)assert.notEqual(link.url,fresh.find(x=>x.team===link.team).url);
    assert.match(await gm.locator('#playerResetStatus').innerText(),/complete/);
    const state=await gm.evaluate(async()=> (await fetch('/s/gamemaster/p/photon-game/api/state')).json());
    assert.equal(state.phase,'setup');assert.deepEqual(state.journey.ready,{});
    for(const p of players){
      await p.page.goto(fresh.find(link=>link.team===p.team).url);await p.page.waitForURL(origin+`/s/${p.team}/p/mobile-ltz/`);
      await p.page.goto(origin+`/s/${p.team}/`);await p.page.waitForSelector('#tabs .tab[data-slug=mobile-ltz]');
      assert.equal(await p.page.locator('#tabs .tab').count(),1);
    }
    await gm.locator('#playerJoin').screenshot({path:path.join(output,'clean-reset-complete.png')});
    await gm.setViewportSize({width:430,height:900});
    await gm.locator('#playerJoin').screenshot({path:path.join(output,'clean-reset-narrow.png')});
    // Lose the successful POST response: the UI must reconcile the committed
    // operation instead of offering a new destructive reset under a new ID.
    await gm.evaluate(()=>{
      const original=window.fetch;
      window.fetch=async function(url,options){
        const response=await original.call(this,url,options);
        if(String(url).endsWith('/player-sessions/clean-reset'))throw Error('Simulated lost response');
        return response;
      };
    });
    await gm.locator('#cleanResetPlayers').click();
    await gm.waitForFunction(()=>document.querySelector('#cleanResetPlayers').textContent==='Clean reset'&&!document.querySelector('#playerJoinCards').hidden);
    assert.equal(await gm.locator('#playerResetStatus').getAttribute('data-error'),'false');
    assert.match(await gm.locator('#playerResetStatus').innerText(),/complete/);
    assert.deepEqual(errors,[]);
    console.log('PASS: connection names/IPs, regeneration isolation, failed stop blocks access, all players redirected, durable retry, fresh QR rejoin, Mobile LTZ-only tabs, lost-response recovery, no browser exceptions.');
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
