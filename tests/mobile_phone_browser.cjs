// Run against tests/mobile_ltz_fixture.py (temporary simulation; no hardware).
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  try{
    const page=await browser.newPage({viewport:{width:844,height:390},isMobile:true,hasTouch:true});
    await page.addInitScript(()=>localStorage.setItem('mobile-ltz:stopped','yes'));
    let states=0,streams=0,commands=0;const errors=[];
    page.on('pageerror',e=>errors.push(e.message));
    await page.route('**/api/state',async route=>{
      states++;
      if(states===1)return route.fulfill({status:502,contentType:'text/html',body:'<html>Bad gateway</html>'});
      return route.continue();
    });
    // Reproduce a phone whose live stream never delivers another event.
    await page.route('**/api/events',route=>{streams++;return route.abort();});
    await page.route('**/api/command',route=>{if(route.request().postDataJSON().action==='stop')return route.continue();commands++;return route.fulfill({status:504,contentType:'text/html',body:'<html>Gateway timeout</html>'});});
    await page.goto('http://127.0.0.1:8117/s/green/p/mobile-ltz/');
    await page.waitForFunction(()=>document.getElementById('feedback').textContent.includes('invalid response (HTTP 502)'));
    await page.locator('#empty').waitFor({state:'hidden',timeout:10000});
    await page.waitForFunction(()=>Number(document.getElementById('fps').textContent)>0);
    const fps=await page.locator('#fps').textContent();
    await page.waitForFunction(()=>!document.getElementById('connect').disabled);
    await page.locator('#connect').click();
    await page.waitForFunction(()=>document.getElementById('feedback').textContent.includes('invalid response (HTTP 504)'));
    await page.locator('#stop').click();
    assert.equal(commands,1,'explicit Stop cancels automatic join retries');
    const before=states;
    await page.waitForTimeout(9000);
    assert.ok(states>before,'a missing stream must keep recovering snapshots even with a cached map');
    assert.ok(streams>=2,'a stalled EventSource is recreated');
    assert.ok(states<15,'recovery stays bounded');
    assert.equal(await page.locator('#empty').isVisible(),false);
    assert.deepEqual(errors,[]);
    await page.screenshot({path:'/tmp/mobile-phone-fix-browser.png'});
    console.log(JSON.stringify({fps,states,streams,commands,errors}));
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
