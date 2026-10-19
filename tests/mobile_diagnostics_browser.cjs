// Isolated fixture only: tests/mobile_ltz_fixture.py. No live game commands.
const assert = require('node:assert/strict');
const {chromium} = require('playwright');
const base = process.env.MOBILE_TEST_URL || 'http://127.0.0.1:8117';
(async () => {
  const browser = await chromium.launch({headless:true, executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  try {
    const page = await browser.newPage({viewport:{width:844,height:390}, isMobile:true, hasTouch:true});
    await page.addInitScript(() => {
      localStorage.setItem('mobile-ltz:stopped', 'yes');
      localStorage.setItem('mobile-ltz:purple:stopped', 'yes');
    });
    const errors = []; let commands = 0;
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => {if (request.url().endsWith('/api/command')) commands++;});
    const camera = enabled => page.request.post(base + '/__test/camera', {data:{enabled,stale:false}});
    await camera(false);
    await page.goto(base + '/s/green/p/mobile-ltz/');
    await page.waitForFunction(() => Number(document.getElementById('fps').textContent) > 0);
    assert.equal(await page.locator('.diagnostics, #updateHz, #updateAge, #prediction, #bufferMs, #framePeak').count(), 0);
    const layouts = [];
    for (const [width,height] of [[844,390],[390,844],[568,320],[320,568]]) {
      await page.setViewportSize({width,height});
      await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
      const layout = await page.evaluate(() => {
        const rect = selector => {
          const r = document.querySelector(selector).getBoundingClientRect();
          return {left:r.left,top:r.top,right:r.right,bottom:r.bottom};
        };
        return {telemetry:rect('.telemetry'), identity:rect('.identity'), expand:rect('#expand'), controls:rect('.connectionControls'),
          facts:[...document.querySelectorAll('.facts > span')].map(el => {
            const r=el.getBoundingClientRect();return {left:r.left,right:r.right,top:r.top,bottom:r.bottom};
          })};
      });
      const intersects = (a,b) => a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
      assert.ok(!intersects(layout.telemetry,layout.identity), 'telemetry cannot overlap the player identity');
      assert.ok(!intersects(layout.telemetry,layout.expand), 'telemetry cannot cover Expand');
      assert.ok(!intersects(layout.telemetry,layout.controls), 'telemetry cannot sit under Connect or Stop: '+JSON.stringify({width,height,...layout}));
      for (const r of layout.facts) assert.ok(r.left >= 0 && r.right <= width && r.top >= 0 && r.bottom <= height, 'all facts fit the viewport');
      layouts.push({width,height,...layout});
      await page.screenshot({path:`/tmp/mobile-diagnostics-${width}x${height}.png`});
    }
    await page.setViewportSize({width:844,height:390});
    const results=[];
    for(const team of ['green','purple']){
      await camera(true);
      await page.goto(base + `/s/${team}/p/mobile-ltz/`);
      await page.waitForFunction(() => !view && Number(document.getElementById('fps').textContent)>0);
      const cameraFps=Number(await page.locator('#fps').textContent());
      assert.equal(await page.locator('.diagnostics, #updateHz, #updateAge, #prediction, #bufferMs, #framePeak').count(),0);
      await page.route('**/*mobile-camera.jpg*',route=>route.abort());
      await page.waitForFunction(() => document.getElementById('fps').textContent==='0');
      await page.unroute('**/*mobile-camera.jpg*');
      await page.waitForFunction(() => Number(document.getElementById('fps').textContent)>0);
      await page.evaluate(() => window.dispatchEvent(new PageTransitionEvent('pagehide',{persisted:true})));
      assert.equal(await page.locator('#fps').textContent(),'—');
      await page.evaluate(() => window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true})));
      await page.waitForFunction(() => !view && Number(document.getElementById('fps').textContent)>0);
      await camera(false);
      await page.waitForFunction(() => view?.levelReady && Number(document.getElementById('fps').textContent)>0);
      const gameFps=Number(await page.locator('#fps').textContent());
      await camera(true);
      await page.waitForFunction(() => !view && Number(document.getElementById('fps').textContent)>0);
      results.push({team,cameraFps,gameFps});
    }
    assert.equal(commands, 0);
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({results, viewports:layouts.map(({width,height})=>({width,height})), commands, errors}));
  } finally {await browser.close();}
})().catch(error => {console.error(error);process.exitCode=1;});
