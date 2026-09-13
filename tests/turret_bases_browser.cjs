// Run ltz_browser_fixture.py first. Uses the real shared renderer and all 12 atlases.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {chromium} = require('playwright');
const origin = 'http://127.0.0.1:' + fs.readFileSync('/tmp/ltz-browser-port', 'utf8');
const scene = JSON.parse(fs.readFileSync('/tmp/ltz-browser-scene.json', 'utf8'));

(async () => {
  const browser = await chromium.launch({headless: true,
    executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  try {
    const page = await browser.newPage({viewport: {width: 1100, height: 850}, deviceScaleFactor: 2});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/turret-preview', route => route.fulfill({contentType: 'text/html', body: `
      <style>body{margin:0;background:#182029;color:#dce9f5;font:16px system-ui}
      canvas{position:absolute;left:0;top:0;width:1696px;height:960px}
      #labels{position:absolute;inset:0;pointer-events:none}span{position:absolute;text-align:center;width:240px}</style>
      <canvas id="mapCanvas" width="1696" height="960"></canvas>
      <canvas id="gameCanvas" width="1696" height="960"></canvas><div id="labels"></div>
      <script src="/s/gamemaster/p/laser-tag-y/tower-defence-view.js"></script>`}));
    await page.goto(origin + '/turret-preview');
    await page.evaluate(scene => {
      scene.towers = scene.towers.slice(0, 12);
      scene.enemies = []; scene.active_enemies = 0; scene.connections = []; scene.projectiles = [];
      scene.core = null; scene.row_barriers = []; scene.paused = true;
      scene.level = {...scene.level, sockets: [], core: {x: 1600, y: 850}, scene: null, paths: {a: []}, path: []};
      scene.presentation = {...scene.presentation, assets: Object.fromEntries(
        Object.entries(scene.presentation.assets).filter(([key]) => key.startsWith('tower/')))};
      const names = ['Machine gun', 'Flamethrower', 'Mortar', 'Tesla Coil'];
      scene.towers.forEach((tower, i) => {
        tower.x = 160 + i % 4 * 250; tower.y = 150 + Math.floor(i / 4) * 250;
        tower.hp = tower.max_hp; tower.last_fire_at = -100; tower.weapon_charge = 0;
        tower.targeting = {...tower.targeting, angle: 0, half_angle: 0, range: 0};
        tower.facing_angle = 0;
        const label = document.createElement('span');
        label.style.left = `${tower.x - 120}px`; label.style.top = `${tower.y + 70}px`;
        label.textContent = `${names[i % 4]} · L${tower.upgrade_level}`;
        document.querySelector('#labels').append(label);
      });
      window.scene = scene;
      window.view = TowerDefenceView.create({sandboxRoot: '/s/gamemaster',
        mapCanvas: document.querySelector('#mapCanvas'), gameCanvas: document.querySelector('#gameCanvas'),
        onAssetStatus: status => window.assets = status});
      view.applyState(scene);
    }, scene);
    await page.waitForFunction(() => window.assets?.loaded > 0 && window.assets.pending === 0);
    await page.evaluate(() => view.renderGame(performance.now()));
    assert.equal(await page.evaluate(() => assets.failed), 0);
    await page.screenshot({path: '/tmp/turret-bases-preview.png'});
    const checks = await page.evaluate(() => {
      const draw = CanvasRenderingContext2D.prototype.drawImage;
      let capture = false, layers = [];
      CanvasRenderingContext2D.prototype.drawImage = function(image, ...args) {
        if (capture && this.canvas.id === 'gameCanvas' && image instanceof HTMLCanvasElement && image.width === 256) {
          layers.push({image, args, transform: this.getTransform()});
        }
        return draw.call(this, image, ...args);
      };
      const failures = [];
      let minimumVisible = 1, maximumExtent = 0;
      const paintLayer = (layer, tower) => {
        const canvas = document.createElement('canvas'); canvas.width = canvas.height = 144;
        const context = canvas.getContext('2d', {willReadFrequently: true});
        context.translate(72 - tower.x, 72 - tower.y);
        const m = layer.transform; context.transform(m.a, m.b, m.c, m.d, m.e, m.f);
        context.drawImage(layer.image, ...layer.args);
        return context.getImageData(0, 0, 144, 144).data;
      };
      for (let direction = 0; direction < 8; direction++) {
        scene.towers.forEach((tower, i) => {
          tower.placement_id = `angle-${direction}-${i}`;
          tower.targeting.angle = direction * Math.PI / 4;
        });
        view.applyState(scene);
        layers = []; capture = true; view.renderGame(performance.now()); capture = false;
        if (layers.length !== 24) throw new Error(`Expected 12 base/head pairs, got ${layers.length}`);
        scene.towers.forEach((tower, i) => {
          const base = paintLayer(layers[i * 2], tower), head = paintLayer(layers[i * 2 + 1], tower);
          let front = 0, visibleFront = 0;
          for (let p = 0; p < base.length; p += 4) {
            const x = p / 4 % 144 - 72, y = Math.floor(p / 4 / 144) - 72;
            if (base[p + 3] > 20 || head[p + 3] > 20) maximumExtent = Math.max(maximumExtent, Math.abs(x), Math.abs(y));
            if (base[p + 3] > 20 && (Math.abs(x) > 44 || Math.abs(y) > 44)) failures.push(`${i}: pedestal exceeds sprite footprint`);
            if (base[p + 3] > 100 && y >= 4) {
              front++; if (head[p + 3] < 100) visibleFront++;
            }
          }
          if (!front) failures.push(`${i}: missing pedestal front`);
          minimumVisible = Math.min(minimumVisible, visibleFront / Math.max(1, front));
        });
      }
      CanvasRenderingContext2D.prototype.drawImage = draw;
      return {failures, minimumVisible, maximumExtent};
    });
    assert.deepEqual(checks.failures, []);
    assert.ok(checks.maximumExtent < 56, 'rotating heads stay inside the unchanged 112 px socket');
    assert.ok(checks.minimumVisible > 0.6, 'at least 60% of every pedestal front remains exposed at all eight aiming angles');
    assert.deepEqual(errors, []);
    console.log('All 12 upgraded turrets passed eight-angle footprint and base-visibility checks:', checks);
  } finally { await browser.close(); }
})().catch(error => {console.error(error); process.exitCode = 1;});
