// Run: node tests/artwork_recovery_renderer.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
let now = 0, timerId = 0;
const timers = new Map(), requested = [], reports = [], drawn = [];
global.performance = {now: () => now};
global.setTimeout = (fn, ms) => { const id = ++timerId; timers.set(id, {fn, ms}); return id; };
global.clearTimeout = id => timers.delete(id);
global.requestAnimationFrame = () => 1;
global.cancelAnimationFrame = () => {};
global.Image = class {
  constructor() { this.width = this.height = this.naturalWidth = this.naturalHeight = 320; }
  set src(url) { this.url = url; requested.push(this); }
};
const context = new Proxy({
  drawImage(image) { drawn.push(image.url); },
  measureText() { return {width: 0}; },
}, {get: (target, key) => key in target ? target[key] : () => {}});
const canvas = () => ({style: {}, getContext: () => context});
global.document = {createElement: canvas};
require('../sandboxes/gamemaster/prototypes/laser-tag-y/tower-defence-view.js');
const view = TowerDefenceView.create({mapCanvas: canvas(), gameCanvas: canvas(),
  onAssetStatus: report => reports.push(report), onAssetError() {}});
const state = revision => ({
  phase: 'setup', level_revision: revision, towers: [], enemies: [],
  level: {width: 1696, height: 960, sockets: [], paths: {}, scene: {
    contract: 'photon.visual-scene', version: 1,
    layers: [{items: [{kind: 'sprite', asset_id: 'tile', x: 0, y: 0, width: 320, height: 320}]}],
  }},
  presentation: {contract: 'photon.level.assets', version: 1, status: 'ready', base: '/art',
    revision: String(revision), assets: {'map/tile': `tile-${revision}.png`, 'tower/machine_gun/head': `head-${revision}.png`}},
});
const settle = () => new Promise(resolve => setImmediate(resolve));
function retry() {
  assert.equal(timers.size, 1, 'one retry timer per failed presentation');
  const [id, timer] = [...timers][0];
  timers.delete(id); now += timer.ms; timer.fn();
}
(async () => {
  view.applyState(state(1));
  const tile = requested.find(image => image.url.includes('tile'));
  const head = requested.find(image => image.url.includes('head'));
  tile.onerror();
  await settle();
  assert.equal(timers.size, 0, 'wait for the rest of the batch before retrying');
  head.onload();
  await settle();
  assert.equal(reports.at(-1).failed, 1);
  assert.equal(reports.at(-1).ready, false);
  retry(); // No new game snapshot is supplied after the failure.
  assert.equal(requested.length, 3, 'retry only the failed image; reuse successful artwork');
  requested.at(-1).onerror();
  await settle();
  assert.equal(reports.at(-1).failed, 1, 'repeated failures do not inflate the unresolved count');
  retry();
  requested.at(-1).onload();
  await settle();
  assert.equal(reports.at(-1).ready, true);
  assert.equal(reports.at(-1).failed, 0);
  assert.equal(reports.at(-1).last_error, null);
  assert.equal(timers.size, 0);
  assert.ok(drawn.includes('/art/tile-1.png'), 'the recovered map is actually drawn');

  view.applyState(state(2));
  requested.slice(-2).forEach(image => image.onerror());
  await settle();
  const obsoleteRetry = [...timers.values()][0].fn;
  view.applyState(state(3));
  assert.equal(timers.size, 0, 'changing artwork cancels the old retry');
  const count = requested.length;
  obsoleteRetry();
  assert.equal(requested.length, count, 'an obsolete timer cannot request or publish old artwork');
  requested.slice(-2).forEach(image => image.onload());
  await settle();
  assert.ok(drawn.includes('/art/tile-3.png'));
  view.applyState(state(4));
  requested.slice(-2).forEach(image => image.onerror());
  await settle();
  view.destroy();
  assert.equal(timers.size, 0, 'destroy releases the retry timer');

  // Exercise the real external-screen status callbacks without another SSE update.
  const html = fs.readFileSync(require.resolve('../sandboxes/gamemaster/prototypes/laser-tag-y/screen.html'), 'utf8');
  const source = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].at(-1)[1];
  const status = {}, readyState = {status: 'ready', phase: 'setup', presentation: {status: 'ready'}};
  let callbacks;
  const streams = [];
  vm.runInNewContext(source, {
    location: {pathname: '/s/gamemaster/p/laser-tag-y/screen'},
    document: {getElementById: () => status, querySelector: () => ({})},
    window: {addEventListener() {}},
    CalibrationDisplay: {create: () => ({update() {}})},
    TowerDefenceView: {create(options) {callbacks = options; return {
      applyState() { options.onAssetStatus({ready: false, requested: 2, loaded: 0, failed: 0, pending: 2}); },
      setFeedConnected() {},
    };},
      presentation: {snapshotReceiver: () => ({})}},
    fetch: async () => ({ok: true, text: async () => JSON.stringify(readyState)}),
    EventSource: class {
      constructor() {streams.push(this);}
      addEventListener() {}
      close() {this.closed = true;}
    },
  });
  await settle();
  assert.equal(streams.length, 0, 'do not occupy the last HTTP connection while initial artwork loads');
  assert.ok(status.textContent.includes('Loading artwork (0/2)'));
  callbacks.onAssetStatus({ready: true, requested: 2, loaded: 2, failed: 0, pending: 0});
  assert.equal(streams.length, 1, 'connect the live game after images finish');
  callbacks.onAssetStatus({ready: false, requested: 3, loaded: 2, failed: 0, pending: 1});
  assert.equal(streams[0].closed, true, 'release the stream connection when replacement artwork loads');
  callbacks.onAssetError('Artwork failed to load: tile.png');
  assert.equal(status.className, 'status error');
  callbacks.onAssetStatus({ready: false, requested: 3, loaded: 2, failed: 1, pending: 0});
  assert.equal(streams.length, 2, 'keep the live game available between retries if an asset remains unavailable');
  assert.equal(status.className, 'status error', 'keep warning until the full presentation is committed');
  callbacks.onAssetStatus({ready: true, requested: 4, loaded: 3, failed: 0, pending: 0});
  assert.equal(streams.length, 2, 'readiness updates do not create duplicate streams');
  assert.equal(status.className, 'status ready');
  assert.ok(!status.textContent.includes('Artwork'), 'clear recovered warning immediately, without another snapshot');
  console.log('Artwork recovery: failed-request retry, batch completion, cache reuse, diagnostics, supersession, cleanup and screen warning passed.');
})().catch(error => {console.error(error); process.exitCode = 1;});
