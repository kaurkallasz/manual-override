// Run against the temporary simulation in tests/mobile_ltz_fixture.py.
const assert=require('node:assert/strict');const {chromium}=require('playwright');
(async()=>{const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
try{const context=await browser.newContext({viewport:{width:844,height:390},isMobile:true,hasTouch:true});const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
const connected=()=>page.waitForFunction(()=>document.getElementById('connection').textContent==='Connected',null,{timeout:25000});
const gm=action=>page.request.post('http://127.0.0.1:8117/__test/command',{data:{action}});
await page.goto('http://127.0.0.1:8117/s/green/p/mobile-ltz/');await connected();console.log('Automatically joined virtual setup.');
await page.reload();await connected();console.log('Refresh restores the same virtual player automatically.');
await gm('start');await page.waitForFunction(()=>state.phase==='running'&&state.enemies.length>0);await connected();assert.equal(await page.locator('#empty').isVisible(),false);
await gm('pause');await page.waitForFunction(()=>state.paused&&!session);await gm('resume');await connected();await gm('reset');await connected();console.log('Start shows orcs; Pause, Resume and Reset preserve automatic joining.');
await page.evaluate(()=>{window.oldToken=session;});await context.setOffline(true);await page.evaluate(()=>liveFeed.source?.dispatchEvent(new Event('error')));await page.waitForTimeout(7000);assert.equal(await page.evaluate(()=>!!session),false);
await context.setOffline(false);await connected();assert.equal(await page.evaluate(()=>session!==window.oldToken),true,'recovery rotates the command token');console.log('Recovered automatically after a seven-second outage.');
// An ambiguous pump response must never cause the action to be replayed.
let pumps=0;await page.route('**/api/command',async route=>{const data=route.request().postDataJSON();if(data.action==='pump'){pumps++;await route.fetch();return route.abort();}return route.continue();});
await page.locator('#pumpMode').focus();await page.locator('#pumpMode').press('Home');await page.waitForFunction(()=>!session);await connected();assert.equal(pumps,1);await page.unroute('**/api/command');
await page.locator('#stop').click();await page.waitForFunction(()=>document.getElementById('connection').textContent==='Stopped');await page.reload();await page.waitForFunction(()=>state?.status==='ready');await page.waitForTimeout(4000);assert.equal(await page.locator('#connection').textContent(),'Stopped');
await gm('start');await page.waitForFunction(()=>state.enemies.length>0);assert.equal(await page.locator('#connection').textContent(),'Stopped','viewing a wave never overrides explicit Stop');assert.equal(await page.locator('#empty').isVisible(),false);
await page.locator('#connect').click();await connected();await gm('reset');await connected();await page.locator('#stop').click();assert.deepEqual(errors,[]);console.log('Stop persists across refresh and Start; orcs remain visible; Connect resumes. No movement replay or JavaScript errors.');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
