/* Render real journey UI with owner-shaped values; no hub, camera or robot. */
const assert = require('node:assert/strict');
const { chromium } = require('playwright');

(async () => {
 const browser = await chromium.launch({ headless: true, executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' });
 try {
  for (const side of ['green', 'purple']) {
   const page = await browser.newPage();
   await page.setContent(`<html data-mobile-team="${side}"><body></body></html>`);
   await page.addScriptTag({ path: 'shared/mobile_ltz/journey.js' });
   await page.evaluate(async side => {
    window.sample = {
     journey: { id: 'render-check', phase: 'calibration', revision: 1, calibration_side: side, active_side: side, deadline: 0, server_time: 100 },
     mobile_calibration_ready: true, mobile_camera: { status: 'ready' },
     mobile_calibration: {
      id: `render-check:${side}`, stage: 'perspective', arrivals: [],
      captures: Object.fromEntries([30, 31, 32, 33, 34, 35].map(n => [n, { marker: n }])),
      draft: { points: {}, parallax_points: Object.fromEntries([31, 35, 33, 34].map(n => [n, {}])), pickup_height: 10 },
      pickup_height: 10, transport_height: null,
     },
    };
    window.request = async (path, value) => {
     if (path === 'journey' && value.action === 'commit') {
      sample.mobile_calibration.transport_height = 50;
      MobileJourney.update(sample, request, async () => {});
      return {};
     }
     return { contract: 'hhh.cal2.history', version: 1, status: 'ready', rows: [] };
    };
    MobileJourney.update(sample, request, async () => {});
    await new Promise(resolve => setTimeout(resolve, 0));
   }, side);
   assert.equal(await page.locator('#calibrationComplete').isDisabled(), true);
   await page.evaluate(() => {
    sample.mobile_calibration.transport_height = 50;
    MobileJourney.update(sample, request, async () => {});
   });
   assert.equal(await page.locator('#calibrationComplete').isEnabled(), true, `${side}: derived heights must immediately enable completion after the countdown ends`);
   assert.match(await page.locator('.calibrationCompletionHint').textContent(), /All measurements saved/);
   assert.equal(await page.locator('[data-height]').count(), 0);
   assert.match(await page.locator('.calibrationHeightSummary').textContent(), /Pickup Z 10.0 mm.*Transport Z 50.0 mm/);
   await page.evaluate(() => {
    sample.mobile_calibration.transport_height = null;
    MobileJourney.update(sample, request, async () => {});
   });
   assert.equal(await page.locator('#calibrationComplete').isDisabled(), true);
   await page.locator('#calibrationCommit').click();
   assert.equal(await page.locator('#calibrationComplete').isEnabled(), true, `${side}: updates received while saving must enable completion when the request finishes`);
   await page.evaluate(() => {
    sample.mobile_calibration_ready=false;
    sample.mobile_calibration.paused=true;
    sample.mobile_camera.status='unavailable';
    MobileJourney.update(sample,request,async()=>{});
   });
   assert.equal(await page.locator('#calibrationComplete').isEnabled(),true,`${side}: saved measurements can complete while disconnected`);
   assert.equal(await page.locator('#calibrationCommit').isDisabled(),true,'Optional movement still requires live access');
   await page.close();
  }
  console.log('Green and Purple completion update immediately when derived heights arrive.');
 } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
