// Isolated fixture: .venv/bin/python tests/mobile_ltz_fixture.py --port 8152
const assert = require('node:assert/strict');
const {webkit, chromium} = require('playwright');
const base = process.env.MOBILE_MEMORY_TEST_URL || 'http://127.0.0.1:8152';
const useChromium = process.env.MOBILE_TEST_BROWSER === 'chromium';
(async () => {
  const browser = await (useChromium ? chromium : webkit).launch({headless: true,
    ...(useChromium ? {executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'} : {})});
  try {
    const results = [];
    for (const team of ['green', 'purple']) {
      const page = await browser.newPage({viewport: {width: 844, height: 390},
        isMobile: true, hasTouch: true, deviceScaleFactor: 3});
      const errors = [], artwork = [];
      page.on('pageerror', error => errors.push(error.message));
      page.on('request', request => {
        if (/game-art|markers\/.*\.png/.test(request.url())) artwork.push(request.url());
      });
      await page.addInitScript(() => {
        for (const team of ['green', 'purple']) localStorage.setItem(team === 'green' ? 'mobile-ltz:stopped' : `mobile-ltz:${team}:stopped`, 'yes');
        const images = [], canvases = [], ImageClass = window.Image;
        window.Image = class extends ImageClass {constructor(...args) {super(...args); images.push(this);}};
        const create = document.createElement.bind(document);
        document.createElement = (tag, ...args) => {
          const node = create(tag, ...args); if (tag === 'canvas') canvases.push(node); return node;
        };
        window.memoryProbe = () => ({
          decodedImages: images.filter(i => i.hasAttribute('src')).reduce((n, i) => n + i.naturalWidth * i.naturalHeight * 4, 0),
          offscreenCanvases: canvases.reduce((n, c) => n + c.width * c.height * 4, 0),
          hiddenCanvases: ['mapCanvas', 'gameCanvas', 'armCanvas'].reduce((n, id) => {
            const c = document.getElementById(id); return n + c.width * c.height * 4;
          }, 0)});
      });
      const camera = enabled => page.request.post(base + '/__test/camera',
        {data: {enabled, stale: false, width: 3840, height: 2160}});
      await camera(true);
      await page.goto(base + `/s/${team}/p/mobile-ltz/`);
      await page.waitForFunction(() => window.TowerDefenceView && turretOverlay.imageAt > 0);
      assert.equal(await page.evaluate(() => view), null, 'physical startup has no simulation renderer');
      assert.equal(artwork.length, 0, 'physical startup downloads no simulation artwork');
      assert.equal(await page.evaluate(() => viewport.w), 3840, 'camera coordinates retain source resolution');
      assert.equal(await page.locator('#playfieldVideo').evaluate(c => c.width), 1920, 'preview stays bounded');
      assert.equal(await page.locator('#playfieldVideo').evaluate(c => c.getContext('2d').getContextAttributes().willReadFrequently), true,
        'camera requests a software-backed surface to avoid iPhone native-memory growth');
      assert.equal(await page.locator('#world').evaluate(e => getComputedStyle(e).willChange), 'auto');
      const physical = await page.evaluate(() => memoryProbe());
      assert.equal(physical.hiddenCanvases, 0);
      await page.evaluate(() => {
        const create = TowerDefenceView.create;
        TowerDefenceView.create = options => create({...options, onAssetStatus: status => {window.assetStatus = status;}});
      });
      let virtual;
      for (let cycle = 0; cycle < 2; cycle++) {
        await camera(false);
        await page.waitForFunction(() => view?.levelReady && assetStatus?.ready && Number(document.getElementById('fps').textContent) > 0);
        virtual = await page.evaluate(() => memoryProbe());
        assert.ok(virtual.decodedImages > 0 && virtual.offscreenCanvases > 0);
        if (cycle === 0) {
          await page.evaluate(async () => {
            window.dispatchEvent(new PageTransitionEvent('pagehide', {persisted: true}));
            // An in-flight script completion must not resurrect a closed view.
            await ensureRenderer();
          });
          assert.equal(await page.evaluate(() => view), null);
          await page.evaluate(() => window.dispatchEvent(new PageTransitionEvent('pageshow', {persisted: true})));
          await page.waitForFunction(() => !booting && view?.levelReady && assetStatus?.ready);
        }
        await camera(true);
        await page.waitForFunction(() => !view && turretOverlay.imageAt > 0);
        const released = await page.evaluate(() => memoryProbe());
        assert.equal(released.hiddenCanvases, 0);
        assert.equal(released.offscreenCanvases, 0, 'mode switch frees renderer caches despite strong probe references');
        // A camera Image can be decoding right now; it is at most one 1080p frame.
        assert.ok(released.decodedImages <= 1920 * 1080 * 4, JSON.stringify(released));
      }
      const count = artwork.length;
      await page.evaluate(() => {
        window.dispatchEvent(new PageTransitionEvent('pagehide', {persisted: true}));
        window.dispatchEvent(new PageTransitionEvent('pageshow', {persisted: true}));
      });
      await page.waitForFunction(() => !booting && turretOverlay.imageAt > 0);
      assert.equal(await page.evaluate(() => view), null);
      assert.equal(artwork.length, count, 'restoring physical play does not recreate hidden artwork');
      assert.deepEqual(errors, []);
      results.push({team, physical, virtual, errors});
      await page.close();
    }
    console.log(JSON.stringify({browser: useChromium ? 'chromium' : 'webkit', results}));
  } finally {await browser.close();}
})().catch(error => {console.error(error); process.exitCode = 1;});
