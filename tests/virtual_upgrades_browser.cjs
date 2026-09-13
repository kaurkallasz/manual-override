// Run virtual_upgrades_fixture.py first. Only its isolated server is contacted.
const assert=require('node:assert/strict'),fs=require('node:fs');
const {chromium}=require('playwright');
const origin='http://127.0.0.1:'+fs.readFileSync('/tmp/virtual-upgrades-port','utf8');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const page=await browser.newPage({viewport:{width:1500,height:1100}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 try {
  await page.goto(origin+'/s/gamemaster/p/laser-tag-y/game');
  await page.waitForSelector('#testUnlocks:not([hidden])');
  await page.click('#maxTestUnlocks');
  await page.waitForFunction(()=>ui.state.virtual_test_loadout?.forcefield===4);
  for(const level of await page.locator('[data-test-track]').evaluateAll(inputs=>inputs.map(e=>e.value)))assert.equal(level,'4');
  const sockets=await page.evaluate(()=>ui.state.level.sockets.map(s=>s.socket_id||s.id));
  for(let i=0;i<4;i++){
   await page.click(`[data-atom="${100+i}"]`);await page.click(`[data-socket="${sockets[i]}"]`);
   await page.waitForFunction(count=>ui.state.towers.length===count,i+1);
  }
  assert.deepEqual(await page.evaluate(()=>ui.state.towers.map(t=>t.upgrade_level)),[4,4,4,4]);
  await page.selectOption('[data-test-track="damage-machine-gun"]','0');
  await page.selectOption('[data-test-track="damage-tesla-coil"]','2');
  await page.selectOption('[data-test-track="forcefield"]','3');
  await page.click('#applyTestUnlocks');
  await page.waitForFunction(()=>ui.state.virtual_test_loadout?.['damage-machine-gun']===0);
  assert.equal(await page.locator('[data-atom="100"]').isDisabled(),true);
  assert.equal(await page.evaluate(()=>ui.state.towers.find(t=>t.tower_type==='tesla_coil').upgrade_level),2);
  assert.equal(await page.evaluate(()=>ui.state.towers.find(t=>t.tower_type==='machine_gun').upgrade_level),4);
  const screen=await browser.newPage();screen.on('pageerror',e=>errors.push(e.message));
  await screen.goto(origin+'/s/gamemaster/p/laser-tag-y/screen');
  await screen.waitForFunction(()=>typeof view!=='undefined'&&view!==null);
  await page.click('#start');await page.waitForFunction(()=>ui.state.phase==='running');await page.click('#pause');
  await page.waitForFunction(()=>ui.state.paused);
  await page.click('#baseTestUnlocks');
  await page.waitForFunction(()=>ui.state.towers.every(t=>t.upgrade_level===1));
  await page.click('#maxTestUnlocks');await page.waitForFunction(()=>ui.state.towers.every(t=>t.upgrade_level===4));
  await page.locator('#testUnlocks').screenshot({path:'/tmp/virtual-test-unlocks.png'});
  await page.reload();await page.waitForFunction(()=>ui.state?.virtual_test_loadout?.forcefield===4);
  assert.equal(await page.locator('#testOverride').isChecked(),true);
  await page.click('#reset');await page.waitForFunction(()=>ui.state.phase==='setup'&&ui.state.towers.length===0);
  assert.equal(await page.locator('[data-test-track="forcefield"]').inputValue(),'4');
  await page.uncheck('#testOverride');await page.click('#applyTestUnlocks');
  await page.waitForFunction(()=>ui.state.virtual_test_loadout===null);
  await page.uncheck('#virtualPlay');await page.waitForFunction(()=>ui.state.virtual_play===false);
  assert.equal(await page.locator('#testUnlocks').isVisible(),false);
  assert.deepEqual(errors,[]);
  await screen.close();
  console.log('Virtual unlock browser checks passed: individual locks, L1–L4 upgrades, live map changes, external view, refresh/reset retention and physical-mode hiding.');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
