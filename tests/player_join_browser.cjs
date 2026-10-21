// Real hub login, join panel, Mobile LTZ bundles and dashboard navigation.
// Start player_join_fixture.py first. This fixture loads no robot/game owners.
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
const path=require('node:path'),fs=require('node:fs');
const origin='http://qr-game.test:8163';
const output=path.resolve(__dirname,'../output/player-join-2026-10-21');
fs.mkdirSync(output,{recursive:true});
(async()=>{
  const browser=await chromium.launch({headless:true,
    executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    args:['--host-resolver-rules=MAP qr-game.test 127.0.0.1','--no-proxy-server']});
  const verified=[];
  try{
    const gmContext=await browser.newContext({viewport:{width:1400,height:1000}});
    const gm=await gmContext.newPage();
    await gm.goto(origin+'/s/gamemaster/p/laser-tag-y/game');
    await gm.locator('[name=password]').fill('fixture-gamemaster');
    await gm.locator('button[type=submit]').click();
    await gm.waitForSelector('.player-join-card img');
    assert.equal(await gm.locator('.player-join-card').count(),2);
    const getLinks=()=>gm.evaluate(async()=>{
      const response=await fetch('/s/gamemaster/api/player-join');return (await response.json()).links;
    });
    let links=await getLinks();
    await gm.locator('#playerJoin').screenshot({path:path.join(output,'gamemaster-qr-cards.png')});
    for(const team of ['green','purple']) await gm.locator(`.player-join-card[data-team=${team}] img`).screenshot({path:path.join(output,`${team}-qr-rendered.png`)});
    await gm.locator('.player-join-card[data-team=green] button').click();
    assert(await gm.locator('#playerJoinCopy').isVisible(),'HTTP clipboard fallback is usable');
    assert.equal(await gm.locator('#playerJoinCopy').inputValue(),links[0].url);
    verified.push('two QR cards, copy-link fallback');
    for(const link of links){
      const context=await browser.newContext({viewport:{width:390,height:844}});
      const page=await context.newPage();
      const urls=[];page.on('request',request=>urls.push(request.url()));
      await page.goto(link.url);
      await page.waitForURL(origin+`/s/${link.team}/p/mobile-ltz/`);
      await page.waitForSelector(`html[data-mobile-team=${link.team}]`);
      assert(!urls.some(url=>url.includes('#join=')||url.includes(link.url.split('#join=')[1])), 'no invitation in HTTP URLs');
      const roles=await page.evaluate(async()=>{
        const other=document.documentElement.dataset.mobileTeam==='green'?'purple':'green';
        return Promise.all([fetch('/s/'+other+'/api/meta'),fetch('/s/gamemaster/api/meta')].map(async response=>(await response).status));
      });
      assert.deepEqual(roles,[401,401]);
      await page.evaluate(team=>{
        localStorage.setItem(`hhh:${team}:lastProto`,'ltx');localStorage.setItem(`hhh:${team}:showOrder`,'1');
      },link.team);
      await page.goto(origin+`/s/${link.team}/#ltx`);
      await page.waitForSelector('#tabs .tab[data-slug=mobile-ltz]');
      assert.equal(await page.locator('#tabs .tab').count(),1);
      assert.match(await page.locator('#frame').getAttribute('src'),/\/p\/mobile-ltz\//);
      assert(await page.locator('#toggleDisabled').isHidden());
      assert(await page.locator('#importLink').isHidden());
      assert(await page.locator('#exportLink').isHidden());
      await page.locator('#togglePlayerTabs').click();
      assert.equal(await page.locator('#tabs .tab').count(),3);
      await page.locator('#tabs .tab[data-slug=ltx] .name').click();
      assert.match(await page.locator('#frame').getAttribute('src'),/\/p\/ltx\//);
      await page.locator('#togglePlayerTabs').click();
      assert.equal(await page.locator('#tabs .tab').count(),1);
      assert.match(await page.locator('#frame').getAttribute('src'),/\/p\/mobile-ltz\//);
      await page.reload();await page.waitForSelector('#tabs .tab[data-slug=mobile-ltz]');
      assert.equal(await page.locator('#tabs .tab').count(),1);
      await page.screenshot({path:path.join(output,`${link.team}-mobile-dashboard.png`)});
      // A second team's code replaces the old team role on this same phone.
      const otherLink=links.find(item=>item.team!==link.team);
      await page.goto(otherLink.url);await page.waitForURL(origin+otherLink.destination);
      assert.equal(await page.evaluate(async team=>(await fetch(`/s/${team}/api/meta`)).status,link.team),401);
      verified.push(`${link.team}: automatic login, real Mobile LTZ, team isolation, stale navigation, show/hide, switching teams`);
      await context.close();
    }
    await gm.locator('#regeneratePlayerCodes').click();
    await gm.waitForFunction(()=>document.querySelector('#playerJoinStatus').textContent.startsWith('Codes valid until'));
    const rotated=await getLinks();assert.notEqual(rotated[0].url,links[0].url);
    const invalidContext=await browser.newContext();const invalid=await invalidContext.newPage();
    await invalid.goto(links[0].url);
    await invalid.waitForFunction(()=>document.querySelector('[role=status]').textContent.includes('expired'));
    assert(!invalid.url().includes('#'));
    assert(await invalid.locator('[name=password]').isEnabled());
    await invalid.locator('[name=password]').fill('fixture-green');await invalid.locator('button[type=submit]').click();
    await invalid.waitForURL(origin+'/s/green/p/mobile-ltz/');
    await invalidContext.close();
    verified.push('regeneration invalidates previous codes; manual password fallback');
    await gm.setViewportSize({width:390,height:844});
    await gm.locator('#playerJoin').scrollIntoViewIfNeeded();
    const layout=await gm.locator('.player-join-card').evaluateAll(cards=>cards.map(card=>{
      const r=card.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width};
    }));
    assert(layout[1].y>layout[0].y);assert.equal(layout[1].x,layout[0].x);
    assert(layout.every(card=>card.x>=0&&card.x+card.width<=390));
    assert(await gm.locator('#playerJoin').evaluate(panel=>Number(getComputedStyle(panel).zIndex)>Number(getComputedStyle(document.getElementById('matchScoreHud')).zIndex)),'QR panel covers the floating score HUD');
    await gm.locator('#playerJoin').screenshot({path:path.join(output,'gamemaster-qr-cards-phone.png')});
    await gm.goto(origin+'/s/green/#ltx');await gm.waitForSelector('#tabs .tab[data-slug=ltx]');
    assert.equal(await gm.locator('#tabs .tab').count(),3,'admin retains full team dashboard');
    assert(await gm.locator('#togglePlayerTabs').isHidden());
    verified.push('responsive cards and unrestricted game master navigation');
    console.log(JSON.stringify({verified,output},null,2));
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
