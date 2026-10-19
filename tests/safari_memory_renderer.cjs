// Deterministic resource-lifetime checks, including cancellation before GC.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const renderer = require.resolve('../sandboxes/gamemaster/prototypes/laser-tag-y/tower-defence-view.js');
const source = fs.readFileSync(renderer, 'utf8');
const scope = {};
vm.runInNewContext(source.slice(source.indexOf('  function releaseRaster('), source.indexOf('  function towerTypeLabel(')) + '\nglobalThis.cache = rasterCache(100);', scope);
const surface = (width, height) => ({width, height, getContext() {}});
const a = surface(8, 8), b = surface(8, 8), c = surface(5, 5);
scope.cache.set('a', a); scope.cache.set('b', b);
assert.equal(a.width * a.height, 0, 'eviction releases the backing store before GC');
scope.cache.set('b', c);
assert.equal(b.width * b.height, 0, 'replacement releases the old backing store');
assert.equal(scope.cache.pixels, 25);
scope.cache.clear();
assert.equal(c.width * c.height, 0); assert.equal(scope.cache.pixels, 0);

const requested = [], canvases = [], reports = [], timers = new Map();
let timer = 0, failReadback = false;
global.setTimeout = fn => {timers.set(++timer, fn); return timer;};
global.clearTimeout = id => timers.delete(id);
global.requestAnimationFrame = () => 1; global.cancelAnimationFrame = () => {};
global.Image = class {
  constructor() {this.naturalWidth = 40; this.naturalHeight = 40;}
  set src(value) {this.url = value; requested.push(this);}
  removeAttribute(name) {assert.equal(name, 'src'); this.url = '';}
};
function canvas() {
  const value = surface(0, 0); value.style = {};
  value.getContext = () => new Proxy({
    measureText: () => ({width: 0}),
    getImageData: (x, y, w, h) => {
      if (failReadback) throw Error('readback failed');
      return {data: new Uint8ClampedArray(w * h * 4)};
    },
  }, {get: (o, k) => o[k] || (() => {})});
  canvases.push(value); return value;
}
global.document = {createElement: canvas};
require(renderer);
const view = TowerDefenceView.create({mapCanvas: canvas(), gameCanvas: canvas(),
  onAssetStatus: value => reports.push(value), onAssetError() {}});
const state = revision => ({phase: 'setup', enemies: [], towers: [], level_revision: revision,
  level: {width: 1696, height: 960, paths: {}, sockets: []},
  presentation: {contract: 'photon.level.assets', version: 1, status: 'ready', base: '/art', revision: String(revision), assets: {
    ...Object.fromEntries(Array.from({length: 12}, (_, i) => [`tower/type${i}/upgrade/2`, `upgrade-${revision}-${i}.png`])),
    'field/upgrade-atlas': `field-${revision}.png`,
    'enemy/breaker/archer-atlas': `archer-${revision}.png`,
  }}});
const settle = () => new Promise(setImmediate);
function completeAll() {
  // Loads that finish open a slot immediately; queued work joins this array.
  for (const image of requested) image.onload?.();
}
(async () => {
  view.applyState(state(1));
  assert.equal(requested.length, 4, 'only four decoders/requests start together');
  const obsolete = requested.map(image => image.onload);
  view.applyState(state(2));
  assert.equal(requested.length, 8, 'obsolete queued work never starts');
  assert.ok(requested.slice(0, 4).every(image => !image.url && !image.onload));
  obsolete.forEach(callback => callback());
  completeAll(); await settle();
  assert.equal(reports.at(-1).ready, true);
  assert.equal(reports.at(-1).loaded, 14);
  assert.equal(reports.at(-1).pending, 0);
  assert.ok(requested.every(image => !image.url), 'processed source atlases are released');
  const visible = canvases.filter(c => c.width === 256 || c.width === 512);
  assert.equal(visible.length, 35, 'all tower layers, field tiers and archer poses survive');

  // Retry failed conversions without losing the currently displayed revision.
  view.applyState(state(3)); failReadback = true;
  completeAll(); await settle();
  assert.equal(reports.at(-1).ready, false);
  assert.ok(visible.every(c => c.width > 0), 'old complete presentation remains usable');
  assert.ok(canvases.every(c => c.width !== 12), 'failed readback releases its scratch canvas');
  assert.equal(timers.size, 1);
  failReadback = false;
  // A new revision supersedes the failed batch and its retry timer.
  view.applyState(state(4)); completeAll(); await settle();
  assert.equal(reports.at(-1).ready, true);
  assert.equal(timers.size, 0);
  assert.ok(visible.every(c => c.width === 0), 'commit releases the previous presentation');

  view.applyState(state(5));
  const count = requested.length;
  view.destroy(); await settle();
  assert.equal(requested.length, count, 'destroy never starts queued work');
  assert.ok(requested.every(image => !image.url && !image.onload));
  assert.ok(canvases.every(c => c.width * c.height === 0));
  view.applyState(state(6));
  assert.equal(requested.length, count, 'late SSE delivery cannot revive a destroyed renderer');
  console.log('PASS: bounded decode, cancellation, atlas release, atomic replacement, failed conversion, cache eviction and teardown');
})().catch(error => {console.error(error); process.exitCode = 1;});
