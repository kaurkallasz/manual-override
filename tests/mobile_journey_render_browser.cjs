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
     if (path === 'journey' && value.action === 'height') {
      sample.mobile_calibration[value.height] = 60;
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
    sample.mobile_calibration.transport_height = 60;
    MobileJourney.update(sample, request, async () => {});
   });
   assert.equal(await page.locator('#calibrationComplete').isEnabled(), true, `${side}: final height must immediately enable completion after the countdown ends`);
   assert.match(await page.locator('.calibrationCompletionHint').textContent(), /All measurements saved/);
   await page.evaluate(() => {
    sample.mobile_calibration.transport_height = null;
    MobileJourney.update(sample, request, async () => {});
   });
   assert.equal(await page.locator('#calibrationComplete').isDisabled(), true);
   await page.locator('[data-height="transport_height"]').click();
   assert.equal(await page.locator('#calibrationComplete').isEnabled(), true, `${side}: updates received while saving must enable completion when the request finishes`);
   await page.close();
  }
  console.log('Green and Purple completion update immediately after the final height capture.');
 } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
