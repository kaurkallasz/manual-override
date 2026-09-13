// Run the real renderer and capture sprite-cache dimensions and body effects.
const assert = require('node:assert/strict');
const images = [], draws = [], arcs = [];
global.requestAnimationFrame = () => 1;
global.cancelAnimationFrame = () => {};
global.Image = class {
  constructor() { this.width = this.height = this.naturalWidth = this.naturalHeight = 320; }
  set src(url) { this.url = url; images.push(this); }
};
function canvas() {
  const surface = {style: {}};
  const context = new Proxy({
    drawImage(image, ...args) { draws.push({image, args, surface}); },
    arc(...args) { arcs.push(args); },
    measureText() { return {width: 10}; },
    createRadialGradient() { return {addColorStop() {}}; },
    createLinearGradient() { return {addColorStop() {}}; },
  }, {get: (target, key) => key in target ? target[key] : () => {}});
  surface.getContext = () => context;
  return surface;
}
global.document = {createElement: canvas};
require('../sandboxes/gamemaster/prototypes/laser-tag-y/tower-defence-view.js');
const gameCanvas = canvas();
const view = global.TowerDefenceView.create({mapCanvas: canvas(), gameCanvas, sandboxRoot: ''});
const state = {
  phase: 'running', paused: true, sim_time: 0, runtime_time: 0, level_revision: 1,
  settings: {brute_size_multiplier: 2},
  enemies: ['grunt', 'brute', 'runner', 'breaker'].map((type, index) => ({
    id: 4 + index * 4, enemy_type: type, x: 200 + index * 300, y: 200,
    facing_x: 1, facing_y: 1, burn_until: 1,
  })),
  towers: [],
  force_field_impacts: [{enemy_id: 8, enemy_type: 'brute', at: 0}],
  level: {width: 1696, height: 960, paths: {}, sockets: []},
  presentation: {contract: 'photon.level.assets', version: 1, status: 'ready',
    base: '/assets', revision: 'one', assets: {
      'enemy/grunt/1': 'grunt.png', 'enemy/brute/1': 'brute.png',
      'enemy/runner/1': 'runner.png', 'enemy/breaker/1': 'breaker.png',
      'effect/flame-burn': 'burn.png', 'effect/force-field-zap-skeleton': 'skeleton.png',
    }},
};
const close = (a, b) => assert.ok(Math.abs(a - b) < 1e-8, `${a} != ${b}`);
(async () => {
  view.applyState(state);
  view.renderGame();
  const fallback = arcs.filter(args => args[0] === 200 || args[0] === 500);
  close(fallback.find(args => args[0] === 500)[2] / fallback.find(args => args[0] === 200)[2], 2);
  for (const image of images) image.onload();
  await new Promise(resolve => setImmediate(resolve));
  view.renderGame();
  const grunt = draws.find(draw => draw.image.url?.endsWith('grunt.png'));
  const brute = draws.find(draw => draw.image.url?.endsWith('brute.png'));
  close(brute.args[2] / grunt.args[2], 2);
  for (const type of ['runner', 'breaker']) {
    const regular = draws.find(draw => draw.image.url?.endsWith(`${type}.png`));
    close(regular.args[2], grunt.args[2]);
  }
  close(grunt.args[2], 44 / 3 * 2);
  for (const draw of [grunt, brute]) {
    close(draw.args[0], -draw.args[2] / 2);
    assert.ok(draw.surface.width >= draw.args[2] * Math.SQRT2, 'rotated body fits cache');
    assert.equal(draw.surface.width, draw.surface.height);
  }
  const burns = draws.filter(draw => draw.image.url?.endsWith('burn.png'));
  close(burns[1].args[2] / burns[0].args[2], 2);
  const skeleton = draws.find(draw => draw.image.url?.endsWith('skeleton.png'));
  close(skeleton.args[2], 31 * 2 * 2 * (1 + Math.sin(8) * 0.06));
  const oldDrawCount = draws.length;
  view.applyState({...state, settings: {brute_size_multiplier: 1}});
  view.renderGame();
  const updated = draws.slice(oldDrawCount).find(draw => draw.image.url?.endsWith('brute.png'));
  assert.ok(updated, 'new run size must not reuse the old cached Brute');
  close(updated.args[2] / grunt.args[2], 1);
  view.destroy();
})().catch(error => { console.error(error); process.exitCode = 1; });
