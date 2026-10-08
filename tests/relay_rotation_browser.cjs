// Browser smoke test against mocked HTTP/SSE only; no local hub or robot access.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright');
const root = path.join(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'sandboxes/gamemaster/prototypes/dobot-mg400-relay/controller.html'), 'utf8');
const theme = fs.readFileSync(path.join(root, 'hub/theme.css'), 'utf8');
const arm = (angle, extra={}) => ({connected:true, feedback_ok:true, feedback_age:.01,
  joints:[90,19,59,angle], pose:[250,10,60,47.5], enabled:false, mode_name:'DISABLED', ...extra});
const snapshot = {arms:{purple:arm(1577.5, {error:true, mode_name:'ERROR', alarm_ids:[70], fault_kind:'joint4_positive_limit'}),
  green:arm(250)}, sides:{}, z_floor:{value:-72, models:{}}, command_log:[]};
(async () => {
  const chrome = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
  const browser = await chromium.launch({headless:true, ...(fs.existsSync(chrome) ? {executablePath:chrome} : {})});
  try {
    const page = await browser.newPage({viewport:{width:1280,height:1000}});
    const errors = [], writes = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.addInitScript(() => {
      window.EventSource = class {constructor(){window.fixtureStream=this;}};
    });
    await page.route('**/*', async route => {
      const request = route.request(), url = new URL(request.url());
      if (request.method() !== 'GET') {writes.push(request.url()); return route.abort();}
      if (url.pathname.endsWith('/api/config')) return route.fulfill({json:{default_links:{}}});
      if (url.pathname.endsWith('/api/state')) return route.fulfill({json:snapshot});
      if (url.pathname === '/theme.css') return route.fulfill({contentType:'text/css', body:theme});
      if (url.pathname === '/p/dobot-mg400-relay/') return route.fulfill({contentType:'text/html', body:html});
      return route.abort();
    });
    await page.goto('http://relay.test/p/dobot-mg400-relay/');
    await page.waitForFunction(() => window.fixtureStream?.onmessage);
    await page.evaluate(state => {
      window.fixtureState=state;
      window.emitFixture = () => window.fixtureStream.onmessage({data:JSON.stringify(window.fixtureState)});
      window.emitFixture();
      window.fixtureTimer=setInterval(window.emitFixture, 100);
    }, snapshot);
    const purple = page.locator('.armcard.purple'), green = page.locator('.armcard.green');
    assert.equal(await purple.locator('.sRotation').textContent(), '1577.5°');
    assert.equal(await green.locator('.sRotation').textContent(), '250.0°');
    assert.match(await purple.locator('.stallWarn').textContent(), /1217.5° above/);
    const colors = await page.evaluate(() => ['.purple .sRotation','.green .sRotation','.purple .stallWarn']
      .map(sel=>getComputedStyle(document.querySelector(sel)).color));
    assert.notEqual(colors[0], colors[1]);
    assert.equal(colors[0], colors[2]);
    for (const width of [1280, 390, 320]) {
      await page.setViewportSize({width,height:1000});
      const fits = await page.evaluate(() => [...document.querySelectorAll('.rotation,.sRotation,.stallWarn')]
        .filter(el=>getComputedStyle(el).display!=='none').every(el=>{
          const r=el.getBoundingClientRect();
          return r.left>=0 && r.right<=innerWidth && el.scrollWidth<=el.clientWidth+1;
        }));
      assert.ok(fits, `Rotation and recovery guidance fit at ${width}px`);
      await purple.locator('.rotation').scrollIntoViewIfNeeded();
      await page.screenshot({path:`/tmp/relay-rotation-${width}.png`});
    }
    await page.evaluate(() => {clearInterval(window.fixtureTimer); window.fixtureStream.onerror();});
    assert.equal(await purple.locator('.sRotation').textContent(), '—');
    assert.match(await purple.locator('.stallWarn').textContent(), /Current angle unavailable/);
    await page.evaluate(() => {window.fixtureStream.onmessage({data:'bad JSON'});});
    assert.equal(await green.locator('.sRotation').textContent(), '—');
    await page.evaluate(() => {window.fixtureState.arms.purple.joints[3]=300;window.emitFixture();});
    assert.equal(await purple.locator('.sRotation').getAttribute('class'), 'sRotation inside');
    assert.match(await purple.locator('.stallWarn').textContent(), /still reports a limit alarm/);
    await page.waitForFunction(() => document.querySelector('.purple .sRotation').textContent==='—');
    assert.deepEqual(errors, []);
    assert.deepEqual(writes, []);
    console.log('Browser J4 monitor: desktop/mobile layouts, colors, SSE loss/recovery/expiry and zero control requests passed.');
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
