// Isolated fixture only: tests/mobile_ltz_fixture.py. No live game commands.
const assert = require('node:assert/strict');
const {chromium} = require('playwright');
(async () => {
  const browser = await chromium.launch({headless:true, executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  try {
    const page = await browser.newPage({viewport:{width:844,height:390}, isMobile:true, hasTouch:true});
    await page.addInitScript(() => localStorage.setItem('mobile-ltz:stopped', 'yes'));
    const errors = []; let commands = 0;
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => {if (request.url().endsWith('/api/command')) commands++;});
    await page.goto('http://127.0.0.1:8117/s/green/p/mobile-ltz/');
    await page.waitForFunction(() => Number(document.getElementById('fps').textContent) > 0
      && Number(document.getElementById('updateHz').textContent) > 0);
    const metrics = await page.evaluate(() => Object.fromEntries(
      ['fps','updateHz','updateAge','prediction','bufferMs','framePeak'].map(id => [id, Number(document.getElementById(id).textContent)])));
    for (const value of Object.values(metrics)) assert.ok(Number.isFinite(value));
    assert.ok(metrics.bufferMs >= 250 && metrics.bufferMs <= 450);
    const layouts = [];
    for (const [width,height] of [[844,390],[390,844],[568,320],[320,568]]) {
      await page.setViewportSize({width,height});
      const layout = await page.evaluate(() => {
        const rect = selector => {
          const r = document.querySelector(selector).getBoundingClientRect();
          return {left:r.left,top:r.top,right:r.right,bottom:r.bottom};
        };
        return {telemetry:rect('.telemetry'), identity:rect('.identity'), expand:rect('#expand'), controls:rect('.connectionControls'),
          diagnostics:[...document.querySelectorAll('.diagnostics span')].map(el => {
            const r=el.getBoundingClientRect();return {left:r.left,right:r.right,top:r.top,bottom:r.bottom};
          })};
      });
      const intersects = (a,b) => a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
      assert.ok(!intersects(layout.telemetry,layout.identity), 'diagnostics cannot overlap the player identity');
      assert.ok(!intersects(layout.telemetry,layout.expand), 'diagnostics cannot cover Expand');
      assert.ok(!intersects(layout.telemetry,layout.controls), 'diagnostics cannot sit under Connect or Stop');
      for (const r of layout.diagnostics) assert.ok(r.left >= 0 && r.right <= width && r.top >= 0 && r.bottom <= height, 'all metrics fit the viewport');
      layouts.push({width,height,...layout});
      await page.screenshot({path:`/tmp/mobile-diagnostics-${width}x${height}.png`});
    }
    await page.setViewportSize({width:844,height:390});
    await page.evaluate(() => {const end = performance.now() + 100; while (performance.now() < end) { /* simulate one slow frame */ }});
    await page.waitForFunction(() => document.getElementById('framePeak').dataset.spike === 'true', null, {timeout:3000});
    assert.equal(commands, 0);
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({metrics, viewports:layouts.map(({width,height})=>({width,height})), frameSpikeDetected:true, commands, errors}));
  } finally {await browser.close();}
})().catch(error => {console.error(error);process.exitCode=1;});
