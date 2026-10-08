// Run only against mobile_api_monitor_fixture.py. No live game commands.
const assert = require('node:assert/strict');
const {chromium} = require('playwright');

async function checkTimeline(browser, base, seed) {
  // Feed deterministic cumulative measurements through the real polling UI.
  // This exercises interval rates, aligned spikes, expiry, gaps and hub resets.
  const page = await browser.newPage({viewport:{width:1440,height:1080}});
  const errors = []; page.on('pageerror', error => errors.push(error.message));
  const origin = Math.floor(Date.now() / 1000);
  const value = structuredClone(seed);
  value.started_at = origin; value.sampled_at = origin; value.recent = [];
  for (const team of Object.values(value.teams)) {
    for (const key of Object.keys(team)) if (typeof team[key] === 'number') team[key] = 0;
    team.samples = {};
  }
  await page.route('**/api/monitor*', route => route.fulfill({json:value}));
  await page.goto(base + '/');
  await page.waitForFunction(() => document.getElementById('connectionStatus').textContent.includes('Live'));
  const rows = page.locator('.timeline-row');
  const readings = () => rows.locator('[data-team=green]').allTextContents();
  async function tick(seconds, generated, mean, options = {}) {
    value.sampled_at = origin + seconds;
    Object.assign(value.teams.green, {generated, build_mean_ms:mean, sse_updates:generated,
      sse_bytes:generated * 2048, http_bytes:generated * 1024, active_streams:1,
      http_errors:generated / 5, ...options});
    await page.waitForFunction(stamp => document.getElementById('updatedAt').textContent.includes(new Date(stamp * 1000).toLocaleTimeString()), value.sampled_at);
  }
  await tick(1, 10, 5);
  assert.deepEqual(await readings(), ['10','10','30','5','1','2']);
  await tick(2, 30, 7);
  assert.deepEqual(await readings(), ['20','20','60','8','1','4']);
  const paths = await rows.locator('.timeline-series[data-side=green]').evaluateAll(nodes => nodes.map(node => node.getAttribute('d')));
  const positions = path => [...path.matchAll(/[ML]([\d.]+),/g)].map(match => Number(match[1]));
  for (const i of [1,2,3,5]) assert.deepEqual(positions(paths[i]), positions(paths[0]), 'spikes share their x coordinates');
  assert.equal(positions(paths[0]).length, 2);
  await rows.nth(0).locator('svg').hover({position:{x:500,y:30}});
  const cursors = await rows.locator('.timeline-cursor').evaluateAll(nodes => nodes.map(node => node.getAttribute('d')));
  assert.ok(cursors[0]); assert.ok(cursors.every(path => path === cursors[0]), 'shared inspection cursor');
  await page.locator('#timeline').focus(); await page.keyboard.press('Escape');
  await page.mouse.move(0, 0);
  await tick(16, 100, 7);
  assert.deepEqual(await readings(), ['—','—','—','—','1','—'], 'missed polling interval is a gap');
  await tick(18, 110, 7);
  const retained = positions(await rows.nth(0).locator('.timeline-series[data-side=green]').getAttribute('d'));
  assert.equal(retained.length, 1, 'measurements older than 15 seconds have expired');
  assert.ok(retained[0] > 900 && retained[0] <= 1000);
  value.started_at = origin + 19;
  await tick(19, 0, 0, {active_streams:0});
  assert.equal(await rows.nth(0).locator('.timeline-series[data-side=green]').getAttribute('d'), '', 'hub restart clears prior history');
  assert.deepEqual(errors, []);
  await page.close();
}

(async () => {
  const browser = await chromium.launch({headless:true, executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  try {
    const page = await browser.newPage({viewport:{width:1440,height:1080}});
    const errors = []; let mutations = 0;
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => {if (request.method() !== 'GET') mutations++;});
    const base = 'http://127.0.0.1:8124/s/gamemaster/p/mobile-ltz-api';
    const initialSnapshots = (await (await page.request.get('http://127.0.0.1:8124/__test/counts')).json()).snapshots;
    await page.goto(base + '/');
    await page.waitForFunction(() => document.getElementById('connectionStatus').textContent.includes('Live'));
    assert.equal((await (await page.request.get('http://127.0.0.1:8124/__test/counts')).json()).snapshots, initialSnapshots);
    await page.evaluate(base => {
      window.fixtureStreams = ['green','purple'].map(side => new EventSource(`${base}/api/events?side=${side}`));
      return fetch(`${base}/api/state?side=green`);
    }, base);
    await page.waitForFunction(() => [...document.querySelectorAll('[data-value="active_streams"]')].every(el => el.textContent === '1'));
    await page.waitForFunction(() => document.getElementById('payload').textContent.includes('mobile_team'));
    const generated = await page.locator('#payload').textContent();
    assert.equal(JSON.parse(generated).mobile_team, 'green');
    assert.ok(JSON.parse(generated).level);
    await page.getByRole('tab', {name:'Emitted SSE packet'}).click();
    await page.waitForFunction(() => document.getElementById('payload').textContent.includes('"kind": "update"'));
    const emitted = JSON.parse(await page.locator('#payload').textContent());
    assert.equal(emitted.contract, 'hub.live'); assert.equal(emitted.state.level, undefined);
    await page.locator('#team').selectOption('purple');
    await page.waitForFunction(() => document.getElementById('payload').textContent.includes('"mobile_team": "purple"'));
    await page.locator('#freeze').click();
    const frozen = await page.locator('#payload').textContent();
    const frozenGraph = await page.locator('.timeline-series[data-side=green]').first().getAttribute('d');
    const before = Number(await page.locator('.team[data-side=purple] [data-value=generated]').textContent());
    await page.waitForFunction(before => Number(document.querySelector('.team[data-side=purple] [data-value=generated]').textContent) > before + 5, before);
    assert.equal(await page.locator('#payload').textContent(), frozen);
    assert.notEqual(await page.locator('.timeline-series[data-side=green]').first().getAttribute('d'), frozenGraph, 'history keeps moving while payload is frozen');
    const downloadPromise = page.waitForEvent('download');
    await page.locator('#download').click();
    const download = await downloadPromise;
    assert.match(download.suggestedFilename(), /mobile-purple-sse-/);
    await page.locator('#freeze').click();
    await page.waitForFunction(frozen => document.getElementById('payload').textContent !== frozen, frozen);
    assert.equal(await page.locator('.timeline-row').count(), 6);
    const timelineBox = await page.locator('.timeline').boundingBox(), inspectorBox = await page.locator('.inspector').boundingBox();
    assert.ok(timelineBox.y + timelineBox.height < inspectorBox.y);
    assert.equal(timelineBox.width, inspectorBox.width, 'history spans the same page width as the inspector');
    await checkTimeline(browser, base, await (await page.request.get(base + '/api/monitor')).json());
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({path:'/tmp/mobile-api-monitor-desktop.png',fullPage:true});
    await page.locator('.timeline').screenshot({path:'/tmp/mobile-api-monitor-timeline.png'});
    await page.setViewportSize({width:390,height:700});
    await page.screenshot({path:'/tmp/mobile-api-monitor-mobile.png'});
    await page.locator('.timeline').screenshot({path:'/tmp/mobile-api-monitor-mobile-timeline.png'});
    await page.locator('.inspector').scrollIntoViewIfNeeded();
    await page.screenshot({path:'/tmp/mobile-api-monitor-mobile-inspector.png'});
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'no page-wide horizontal overflow');
    await page.evaluate(() => window.fixtureStreams.forEach(stream => stream.close()));
    await page.waitForFunction(() => [...document.querySelectorAll('[data-value="active_streams"]')].every(el => el.textContent === '0'), null, {timeout:10000});
    assert.equal(mutations, 0); assert.deepEqual(errors, []);
    const counts = await (await page.request.get('http://127.0.0.1:8124/__test/counts')).json();
    assert.equal(counts.commands, 0);
    console.log(JSON.stringify({passiveBeforeClients:true,teams:2,generatedAndEmittedVerified:true,timeline:{rows:6,aligned:true,historySeconds:15,expiry:true,gaps:true,restart:true},freeze:true,download:true,viewports:[1440,390],closedStreams:true,mutations,errors}));
  } finally {await browser.close();}
})().catch(error => {console.error(error);process.exitCode=1;});
