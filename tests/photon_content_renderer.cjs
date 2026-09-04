// Exercise the real renderer with a deterministic Canvas/Image harness.
const assert = require('node:assert/strict');
const requested = [], drawn = [], assetReports = [];
global.requestAnimationFrame = () => 1;
global.cancelAnimationFrame = () => {};
global.Image = class {
  constructor() { this.width = this.height = this.naturalWidth = this.naturalHeight = 320; }
  set src(url) { this.url = url; requested.push(this); }
};
const context = new Proxy({
  drawImage(image) { drawn.push(image.url); },
  measureText() { return {width: 10}; },
  createRadialGradient() { return {addColorStop() {}}; },
  createLinearGradient() { return {addColorStop() {}}; },
}, {get(target, key) { return key in target ? target[key] : () => {}; }});
const canvas = () => ({getContext: () => context, style: {}});
global.document = {createElement: canvas};
require('../sandboxes/gamemaster/prototypes/laser-tag-y/tower-defence-view.js');
const view = global.TowerDefenceView.create({
  sandboxRoot: '/s/gamemaster', mapCanvas: canvas(), gameCanvas: canvas(),
  onAssetStatus: value => assetReports.push(value),
});
const state = {
  status: 'ready', phase: 'setup', level_revision: 1, enemies: [], towers: [],
  level: {width: 1696, height: 960, sockets: [], paths: {a: [[0, 0], [100, 100]]},
    scene: {contract: 'photon.visual-scene', version: 1, layers: [
      {items: [{kind: 'sprite', asset_id: 'test', x: 0, y: 0, width: 320, height: 320}]},
    ]}},
  presentation: {contract: 'photon.level.assets', version: 1, status: 'ready',
    base: '/p/content-owner/assets', revision: 'one', assets: {'map/test': 'test.png?v=one'}},
};
(async () => {
  view.applyState(state);
  assert.equal(requested.length, 1);
  assert.equal(assetReports.at(-1).pending, 1);
  assert.equal(requested[0].url, '/s/gamemaster/p/content-owner/assets/test.png?v=one');
  view.applyState(state);
  assert.equal(requested.length, 1, 'unchanged snapshots do not refetch images');
  view.applyState({...state, presentation: {...state.presentation, revision: 'two', assets: {'map/test': 'test.png?v=two'}}});
  assert.equal(requested.length, 2, 'art-only revision loads at unchanged layout revision');
  requested[1].onload();
  await new Promise(resolve => setImmediate(resolve));
  requested[0].onload();
  await new Promise(resolve => setImmediate(resolve));
  assert.ok(drawn.includes('/s/gamemaster/p/content-owner/assets/test.png?v=two'));
  assert.ok(!drawn.includes('/s/gamemaster/p/content-owner/assets/test.png?v=one'), 'late old image cannot overwrite new art');
  assert.equal(assetReports.at(-1).loaded, 1, 'superseded image does not inflate current counts');
  assert.equal(assetReports.at(-1).pending, 0);
  view.applyState({...state, presentation: null});
  view.applyState(state);
  assert.equal(requested.length, 3, 'unavailable assets can recover without reload');
  requested[2].onload();
  await new Promise(resolve => setImmediate(resolve));
  view.applyState({...state, presentation: {...state.presentation, revision: 'failed', assets: {'map/test':'missing.png'}}});
  requested[3].onerror();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(assetReports.at(-1).failed, 1);
  assert.equal(assetReports.at(-1).pending, 0);
  assert.ok(assetReports.at(-1).last_error.includes('missing.png'));
  view.destroy();
})().catch(error => { console.error(error); process.exitCode = 1; });
