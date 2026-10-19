// Isolated fixture only: python tests/mobile_ltz_fixture.py --port 8152
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {createHash} = require('node:crypto');
const {chromium} = require('playwright');
const base = process.env.MOBILE_MEMORY_TEST_URL || 'http://127.0.0.1:8152';
const renderer = '/s/gamemaster/p/mobile-ltz-api/api/renderer.js';
const baseline = process.env.MEMORY_BASELINE_RENDERER;
(async () => {
  const browser = await chromium.launch({headless: true,
    executablePath: process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  try {
    const page = await browser.newPage({viewport: {width: 844, height: 390}, isMobile: true, hasTouch: true});
    const errors = []; page.on('pageerror', error => errors.push(error.message));
    if (baseline) await page.route('**' + renderer, route => route.fulfill({contentType: 'text/javascript',
      body: fs.readFileSync(require.resolve('../sandboxes/gamemaster/prototypes/laser-tag-y/breaker-renderer.js'), 'utf8') + '\n' + fs.readFileSync(baseline, 'utf8')}));
    await page.goto(base + '/s/gamemaster/p/mobile-ltz-api/api/state');
    await page.setContent('<canvas id="map" style="width:844px"></canvas><canvas id="game" style="width:844px"></canvas>');
    await page.evaluate(() => {
      // Keep probes alive deliberately: release must not depend on when GC runs.
      const images = [], canvases = [], OriginalImage = window.Image;
      const createElement = document.createElement.bind(document);
      document.createElement = (tag, ...args) => {
        const value = createElement(tag, ...args);
        if (tag === 'canvas') canvases.push(value);
        return value;
      };
      let pending = 0, peak = 0;
      window.Image = class extends OriginalImage {
        constructor(...args) {
          super(...args); images.push(this);
          pending++; peak = Math.max(peak, pending);
          const done = () => {pending--; this.removeEventListener('load', done); this.removeEventListener('error', done);};
          this.addEventListener('load', done); this.addEventListener('error', done);
        }
      };
      window.memoryProbe = () => ({peakRequests: peak,
        decodedImageBytes: images.filter(i => i.hasAttribute('src')).reduce((n, i) => n + i.naturalWidth * i.naturalHeight * 4, 0),
        canvasBytes: canvases.reduce((n, c) => n + c.width * c.height * 4, 0),
        sourceAtlases: images.filter(i => i.hasAttribute('src') && /\/upgrades\/|archer-atlas/.test(i.src)).length});
    });
    await page.addScriptTag({url: base + renderer});
    await page.evaluate(async () => {
      window.fixtureState = await (await fetch('/s/gamemaster/p/mobile-ltz-api/api/state')).json();
      window.makeView = () => {
        window.assetStatus = null;
        window.testView = TowerDefenceView.create({sandboxRoot: '/s/gamemaster',
          mapCanvas: document.getElementById('map'), gameCanvas: document.getElementById('game'),
          onAssetStatus: status => window.assetStatus = status});
        testView.applyState(fixtureState);
      };
      makeView();
    });
    await page.waitForFunction(() => assetStatus?.ready, null, {timeout: 60000});
    const loaded = await page.evaluate(() => memoryProbe());
    const map = await page.evaluate(() => document.getElementById('map').toDataURL());
    let stressed = null;
    if (!baseline) {
      stressed = await page.evaluate(() => {
        // Force repeated sprite/glow cache invalidation with real decoded art.
        // Strong probes ensure old backing stores cannot hide behind browser GC.
        for (let step = 0; step < 80; step++) {
          const snapshot = {...fixtureState, phase: 'running', paused: true,
            server_time: fixtureState.server_time + step + 1, sim_time: step / 8, runtime_time: step / 8,
            settings: {...fixtureState.settings, brute_size_multiplier: 1 + step % 4},
            enemies: Array.from({length: 256}, (_, i) => ({id: i + 1, enemy_type: 'brute',
              x: 100 + i % 16 * 80, y: 100 + Math.floor(i / 16) * 40,
              facing_x: Math.cos(i / 16 * Math.PI * 2), facing_y: Math.sin(i / 16 * Math.PI * 2),
              hp: 100, max_hp: 100, burn_until: 999, electrocuted_until: 999, electrocution_intensity: .8}))};
          testView.applyState(snapshot); testView.renderGame();
        }
        return memoryProbe();
      });
      assert.ok(stressed.canvasBytes < 64 * 1024 * 1024, 'retired caches release buffers during play, before GC');
      assert.equal(stressed.decodedImageBytes, loaded.decodedImageBytes);
    }
    await page.evaluate(() => testView.destroy());
    const released = await page.evaluate(() => memoryProbe());
    if (!baseline) {
      assert.ok(loaded.peakRequests <= 4, JSON.stringify(loaded));
      assert.equal(loaded.sourceAtlases, 0, 'only derived runtime sprites retain storage');
      assert.equal(released.decodedImageBytes, 0, 'destroy releases decoded images');
      assert.equal(released.canvasBytes, 0, 'destroy releases all owned offscreen canvases');
      for (let run = 0; run < 3; run++) {
        await page.evaluate(() => makeView());
        await page.waitForFunction(() => assetStatus?.ready, null, {timeout: 60000});
        assert.equal(await page.evaluate(() => document.getElementById('map').toDataURL()), map, 'restoring retains identical map artwork');
        await page.evaluate(() => testView.destroy());
        assert.equal(await page.evaluate(() => memoryProbe().canvasBytes), 0, 'repeated lifecycle retains no canvas buffers');
      }
      await page.addInitScript(() => {
        localStorage.setItem('mobile-ltz:stopped', 'yes');
        localStorage.setItem('mobile-ltz:purple:stopped', 'yes');
      });
      let commands = 0;
      await page.route('**/api/command*', route => {commands++; return route.abort();});
      for (const team of ['green', 'purple']) {
        await page.goto(base + `/s/${team}/p/mobile-ltz/`);
        await page.waitForFunction(() => view?.levelReady && Number(document.getElementById('fps').textContent) > 0);
        // Exercise the same teardown/restoration used by Safari's page cache.
        await page.evaluate(() => {
          window.dispatchEvent(new PageTransitionEvent('pagehide', {persisted: true}));
          window.dispatchEvent(new PageTransitionEvent('pageshow', {persisted: true}));
        });
        await page.waitForFunction(() => view?.levelReady && document.getElementById('gameCanvas').width === 1696
          && Number(document.getElementById('fps').textContent) > 0);
        assert.equal(await page.locator('#login').evaluate(el => el.open), false);
      }
      assert.equal(commands, 0, 'memory checks never issue gameplay or robot commands');
    }
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({baseline: !!baseline, loaded, stressed, released,
      mapHash: createHash('sha256').update(map).digest('hex'), errors}));
  } finally { await browser.close(); }
})().catch(error => {console.error(error); process.exitCode = 1;});
