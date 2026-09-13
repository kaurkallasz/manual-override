// Real UI + isolated Flask store. Run ltz_browser_fixture.py first.
const assert=require('node:assert/strict'),fs=require('node:fs');
const {chromium}=require('playwright');
const origin='http://127.0.0.1:'+fs.readFileSync('/tmp/ltz-browser-port','utf8');
const scene=JSON.parse(fs.readFileSync('/tmp/ltz-browser-scene.json','utf8'));
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const errors=[];
 try {
  const page=await browser.newPage({viewport:{width:1500,height:1100}});page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/photon-game/api/events?view=configuration',r=>r.fulfill({contentType:'text/event-stream',body:'data: '+JSON.stringify({previews:scene.configuration.orc_previews})+'\n\n'}));
  await page.goto(origin+'/s/green/p/ltz-score/');
  await page.waitForSelector('#historyChart circle');
  assert.equal(await page.locator('#historyRows tr').count(),6);
  assert.equal(await page.locator('.upgrade-card').count(),18);
  assert.equal(await page.getByText('Tesla Coil',{exact:true}).count(),1);
  const companionCards=await page.locator('.damage.level-4').evaluateAll(cards=>cards.map(card=>({
   text:card.querySelector('.card-copy p').textContent,
   fits:card.querySelector('.card-copy p').getBoundingClientRect().bottom<=card.querySelector('.buy-button').getBoundingClientRect().top,
  })));
  assert.equal(companionCards.length,4);assert.ok(companionCards.every(card=>card.text.includes('companion')&&card.fits));
  const order=await page.evaluate(()=>document.querySelector('#tracks').compareDocumentPosition(document.querySelector('#player-statistics'))&Node.DOCUMENT_POSITION_FOLLOWING);assert.ok(order);
  await page.selectOption('#metric','time');
  assert.equal(await page.locator('#historyChart circle').count(),6);
  assert.match(await page.locator('#historyChart svg').getAttribute('aria-label'),/lower is better/);
  await page.locator('#historyChart circle').first().focus();
  assert.match(await page.locator('#pointDetails').textContent(),/settings revision/);
  await page.screenshot({path:'/tmp/ltz-score-desktop.png',fullPage:true});
  await page.selectOption('#controlSelect','2');
  await page.waitForFunction(()=>document.querySelector('#runStatus').textContent.includes('Selected: Cartesian XYZ'));
  await page.reload();await page.waitForFunction(()=>document.querySelector('#controlSelect').value==='2');
  await page.setViewportSize({width:390,height:844});await page.screenshot({path:'/tmp/ltz-score-mobile.png',fullPage:true});
  await page.goto(origin+'/s/purple/p/ltz-score/');
  await page.waitForFunction(()=>document.querySelector('#saveStatus').textContent.includes('Saved'));
  await page.fill('#playerName','Browser Newcomer');await page.click('#createPlayer');
  await page.waitForFunction(()=>document.querySelector('#statsPlayer').textContent.includes('Browser Newcomer'));
  assert.equal(await page.locator('#scoreValue').textContent(),'0');
  assert.equal(await page.locator('#controlSelect option:disabled').count(),3);
  await page.reload();await page.waitForFunction(()=>document.querySelector('#statsPlayer').textContent.includes('Browser Newcomer'));
  await page.click('#releasePlayer');await page.waitForFunction(()=>document.querySelector('#scoreValue').textContent==='—');
  await page.close();
  for(const target of ['game','screen']){
   const map=await browser.newPage({viewport:{width:1696,height:1100}});map.on('pageerror',e=>errors.push(e.message));
   await map.addInitScript(()=>{
    window.__assets=null;window.__upgradedDraws=0;
    let api;Object.defineProperty(window,'TowerDefenceView',{get:()=>api,set(value){api=value;const create=value.create;value.create=options=>create({...options,onAssetStatus:s=>{window.__assets=s;options.onAssetStatus?.(s);}});}});
    const draw=CanvasRenderingContext2D.prototype.drawImage;CanvasRenderingContext2D.prototype.drawImage=function(image,...args){if(this.canvas.id==='gameCanvas'&&image instanceof HTMLCanvasElement&&image.width===256)window.__upgradedDraws++;return draw.call(this,image,...args);};
   });
   await map.route('**/laser-tag-y/api/events*',r=>r.fulfill({contentType:'text/event-stream',body:'data: '+JSON.stringify(scene)+'\n\n'}));
   await map.goto(origin+'/s/gamemaster/p/laser-tag-y/'+target);
   await map.waitForFunction(()=>window.__assets?.loaded>0&&window.__assets.pending===0,{timeout:30000});
   const assets=await map.evaluate(()=>({assets:window.__assets,upgrades:window.__upgradedDraws}));
   assert.equal(assets.assets.failed,0);assert.ok(assets.upgrades>=24,'base and head layers are drawn for upgraded towers');
   await map.screenshot({path:'/tmp/ltz-map-'+target+'.png',fullPage:true});
   await map.close();
  }
  assert.deepEqual(errors,[]);console.log('LTZ browser checks passed: persistence, history, tier selection, new profiles, 12 upgraded towers on both map views.');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
