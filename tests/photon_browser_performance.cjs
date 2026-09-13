// Isolated browser replay: real Y pages/assets, synthetic authoritative input.
// NODE_PATH=<Playwright packages> node tests/photon_browser_performance.cjs \
//   /tmp/photon-performance-fixture.json 600 2 [/tmp/old-renderer.js]
const fs = require('node:fs'), path = require('node:path');
const {chromium} = require('playwright');
const root = path.resolve(__dirname, '..');
const fixture = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const seconds = Number(process.argv[3] || 30), views = Number(process.argv[4] || 1);
const alternateRenderer = process.argv[5];
const output = process.env.PHOTON_PERF_OUTPUT || '/tmp/photon-browser-performance.json';

(async () => {
  const browser = await chromium.launch({headless: true, executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  const pages = [], errors = [];
  try {
    for (let i = 0; i < views; i++) {
      const page = await browser.newPage({viewport: {width: 1800, height: 1200}});
      page.on('pageerror', error => errors.push(error.message));
      await page.route('http://photon.test/**', async route => {
        const pathname = new URL(route.request().url()).pathname;
        if (pathname.endsWith('/api/state')) return route.fulfill({json: fixture});
        const relative = pathname.replace(/^\/s\/gamemaster\/p\//, '');
        let file = path.resolve(root, 'sandboxes/gamemaster/prototypes', relative);
        if (relative === 'laser-tag-y/game') file = path.join(file, '../index.html');
        if (relative === 'laser-tag-y/screen') file += '.html';
        if (relative === 'laser-tag-y/tower-defence-view.js' && alternateRenderer) file = alternateRenderer;
        if (pathname === '/theme.css') return route.fulfill({body: '', contentType: 'text/css'});
        if (!file.startsWith(root + path.sep) && file !== alternateRenderer) return route.abort();
        if (fs.existsSync(file) && fs.statSync(file).isFile()) return route.fulfill({path: file});
        return route.fulfill({status: 404, body: 'Fixture route unavailable'});
      });
      await page.addInitScript(({fixture}) => {
        window.__metrics = {fps: [], passes: [], frames: [], longTasks: [], assets: null};
        const clear = CanvasRenderingContext2D.prototype.clearRect;
        CanvasRenderingContext2D.prototype.clearRect = function(...args) {
          if (this.canvas.id === 'gameCanvas') window.__metrics.frames.push(performance.now());
          return clear.apply(this, args);
        };
        new PerformanceObserver(list => {
          for (const entry of list.getEntries()) window.__metrics.longTasks.push(entry.duration);
        }).observe({entryTypes: ['longtask']});
        let api;
        Object.defineProperty(window, 'TowerDefenceView', {get: () => api, set(value) {
          api = value;
          if (!value.presentation.snapshotReceiver) value.presentation.snapshotReceiver = apply => ({full: apply, update: apply});
          const create = value.create;
          value.create = options => create({...options,
            onPerformance: value => window.__metrics.passes.push(value),
            onFps: value => {window.__metrics.fps.push(value); options.onFps?.(value);},
            onAssetStatus: value => {window.__metrics.assets = value; options.onAssetStatus?.(value);},
          });
        }});
        // This feed cannot reach a real game, settings store or hardware.
        window.EventSource = class {
          constructor() {
            this.listeners = {};
            let tick = 0;
            this.timer = setInterval(() => {
              const state = structuredClone(fixture);
              state.sim_time += ++tick * .1; state.runtime_time += tick * .1;
              for (const enemy of state.enemies) {
                enemy.x += Math.sin(tick * .03 + enemy.id) * 18;
                if (enemy.burn_until) enemy.burn_until = state.sim_time + 1;
                if (enemy.electrocuted_until) enemy.electrocuted_until = state.sim_time + 1;
              }
              for (const tower of [...state.towers, ...(state.companions || [])]) tower.last_fire_at = state.sim_time;
              if (fixture.__rowTransitions) {
                const mask = Math.floor(tick / 20) % 16;
                state.row_topology_revision = Math.floor(tick / 20);
                for (const [index, row] of (state.row_barriers || []).entries()) {
                  row.powered = Boolean(mask & (1 << index));
                  row.active_count = row.powered ? 3 : 2;
                  row.changed_at = state.runtime_time - (tick % 20) * .1;
                }
              }
              if (fixture.__peakEffects) {
                const progress = (tick % 30) / 30;
                state.core_sequence = {...state.core_sequence, stage: 'detonating', detonation_progress: progress, detonation_radius: 950 * progress};
                for (const enemy of state.enemies) enemy.burn_until = state.sim_time + 1;
                const mortars = [...state.towers, ...(state.companions || [])].filter(tower => tower.tower_type === 'mortar');
                state.projectiles = mortars.map((tower, i) => ({tower_id: tower.placement_id, launch_at: state.sim_time - progress, impact_at: state.sim_time + 1 - progress, origin_x: tower.x, origin_y: tower.y, target_x: 600 + i * 100, target_y: 500}));
                state.mortar_impacts = mortars.map((tower, i) => ({projectile_id: i, impact_at: state.sim_time - .15, x: 600 + i * 100, y: 500, blast_radius: 80}));
              }
              if (tick === 1) this.onopen?.();
              const usePatch = tick > 1 && this.listeners.update && !fixture.__fullOnly;
              if (usePatch) for (const key of ['level','presentation','configuration','settings','loadout','force_field_blockers','row_barrier_geometry']) delete state[key];
              (usePatch ? this.listeners.update : this.onmessage)?.({data: JSON.stringify(state)});
            }, 100);
          }
          addEventListener(name, fn) {this.listeners[name] = fn;}
          close() {clearInterval(this.timer);}
        };
      }, {fixture: {...fixture, __fullOnly: Boolean(alternateRenderer)}});
      await page.goto(`http://photon.test/s/gamemaster/p/laser-tag-y/${i === 0 ? 'game' : 'screen'}`);
      await page.waitForFunction(() => window.__metrics.assets?.requested > 0 && window.__metrics.assets.pending === 0, {timeout: 60000});
      await page.waitForTimeout(3000);
      pages.push(page);
    }
    for (const page of pages) await page.evaluate(() => {
      document.dispatchEvent(new Event('visibilitychange'));
      window.__metrics.fps = []; window.__metrics.passes = []; window.__metrics.frames = []; window.__metrics.longTasks = [];
    });
    console.log(`Replay started: ${fixture.enemies.length} enemies, ${fixture.towers.length} towers, ${views} views, ${seconds}s`);
    for (let elapsed = 0; elapsed < seconds;) {
      const step = Math.min(30, seconds - elapsed);
      await new Promise(resolve => setTimeout(resolve, step * 1000)); elapsed += step;
      console.log(JSON.stringify({elapsed, views: await Promise.all(pages.map(page => page.evaluate(() => ({fps: window.__metrics.fps.at(-1), quality: window.__metrics.passes.at(-1)?.quality, drawMs: window.__metrics.passes.at(-1)?.drawMs}))))}));
    }
    const results = await Promise.all(pages.map(page => page.evaluate(() => {
      const m = window.__metrics;
      const quantile = (values, fraction) => [...values].sort((a,b) => a-b)[Math.min(values.length - 1, Math.floor(values.length * fraction))];
      const intervals = m.frames.slice(1).map((at, i) => at - m.frames[i]);
      const fps = m.fps.filter(value => value != null);
      return {samples: fps.length, minFps: Math.min(...fps), medianFps: quantile(fps,.5), maxFps: Math.max(...fps), belowTarget: fps.filter(fps => fps <= 30).length, intervalP95: quantile(intervals,.95), intervalP99: quantile(intervals,.99), longTasks: m.longTasks.length, assets: m.assets, passes: m.passes.slice(-5), heapBytes: performance.memory?.usedJSHeapSize};
    })));
    await pages[0].screenshot({path: output.replace(/\.json$/, '.png')});
    fs.writeFileSync(output, JSON.stringify({seconds, views, alternateRenderer, results, errors}, null, 2));
    console.log(JSON.stringify({results, errors, output}));
    if (errors.length || results.some(result => result.assets?.failed)) process.exitCode = 1;
  } finally {await browser.close();}
})().catch(error => {console.error(error); process.exitCode = 1;});
