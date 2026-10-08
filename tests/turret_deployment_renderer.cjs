// Run: node tests/turret_deployment_renderer.cjs
// Replay delayed authoritative deployments through the real gamefield renderer.
const assert = require('node:assert/strict');
let now = 1000;
const draws = [];
global.performance = {now: () => now};
global.requestAnimationFrame = () => 1;
global.cancelAnimationFrame = () => {};
function canvas() {
  const context = new Proxy({
    drawImage(image) { draws.push({image: image.src}); },
    measureText() { return {width: 0}; },
    createRadialGradient(...geometry) {
      const gradient = {geometry, colors: [], addColorStop(at, color) { this.colors.push(color); }};
      draws.push(gradient);
      return gradient;
    },
  }, {get: (target, key) => key in target ? target[key] : () => {}});
  return {style: {}, getContext: () => context};
}
global.document = {hidden: false, createElement: canvas, addEventListener() {}, removeEventListener() {}};
global.Image = class {
  constructor() { this.width = this.naturalWidth = 8064; this.height = this.naturalHeight = 112; }
  set src(value) { this.url = value; queueMicrotask(() => this.onload()); }
  get src() { return this.url; }
};
require('../sandboxes/gamemaster/prototypes/laser-tag-y/tower-defence-view.js');
const view = TowerDefenceView.create({mapCanvas: canvas(), gameCanvas: canvas()});
let state = {
  run_id: 'first', status: 'ready', phase: 'setup', runtime_time: 10, sim_time: 0,
  level_revision: 1, level: {width: 1696, height: 960, sockets: [], paths: {}},
  presentation: {contract: 'photon.level.assets', version: 1, status: 'ready', base: '/art', revision: 1,
    assets: {'tower/machine_gun/activation': 'activation.png'}},
  towers: [], enemies: [], companions: [],
};
const tower = {placement_id: 'one', socket_id: 'one', x: 400, y: 400,
  tower_type: 'machine_gun', owner: 'purple', hp: 100, max_hp: 100,
  activation_started_at: 10, aim_instance: 'first', targeting: {range: 0}};
function update(patch) { state = {...state, ...patch}; view.applyState(state); }
function render() {
  draws.length = 0;
  view.renderGame(now);
  return draws.filter(draw => draw.colors?.some(color => color.startsWith('rgba(73,255,136,')));
}
(async () => {
  update({});
  await new Promise(resolve => setImmediate(resolve));
  update({runtime_time: 10.9, towers: [{...tower}]});
  let flashes = render();
  assert.equal(flashes.length, 1, 'a deployment first delivered 900 ms late still flashes');
  assert.ok(draws.findIndex(draw => draw.image === '/art/activation.png') < draws.indexOf(flashes[0]),
    'deployment art cannot cover the green flash');
  const peak = flashes[0].colors[0];
  now += 100;
  assert.equal(render()[0].colors[0], peak, 'hold a visible peak before fading');
  now += 300;
  update({runtime_time: 11.3});
  assert.notEqual(render()[0].colors[0], peak, 'repeated snapshots do not restart the cue');
  now += 450;
  assert.equal(render().length, 0, 'the cue expires even when the game feed stalls');
  update({runtime_time: 11.4});
  assert.equal(render().length, 0, 'an expired cue does not replay on the next update');
  update({towers: [{...tower, aim_instance: 'replacement', owner: 'green', activation_started_at: 11}]});
  assert.equal(render().length, 1, 'a replacement at the same socket flashes for Green too');
  update({run_id: 'second'});
  assert.equal(render()[0].colors[0], peak, 'new runs reset presentation history');
  update({towers: []});
  assert.equal(render().length, 0);
  update({towers: [{...tower, activation_started_at: 0}]});
  assert.equal(render().length, 0, 'historical already-deployed turrets do not flash');
  update({towers: [{...tower, destroyed: true}]});
  assert.equal(render().length, 0, 'destroyed turrets do not flash');
  for (const stamp of [null, undefined, NaN, Infinity, 'invalid']) {
    update({towers: [{...tower, activation_started_at: stamp}]});
    assert.equal(render().length, 0, 'missing or malformed deployment timestamps do not flash');
  }
  update({towers: [{...tower, activation_started_at: 11.4001}]});
  assert.equal(render().length, 0, 'do not flash before authoritative deployment begins');
  update({runtime_time: 11.5});
  assert.equal(render().length, 1, 'timestamp rounding does not permanently suppress the cue');
  // Missing artwork still gets the overlay above the fallback turret.
  update({towers: [{...tower, tower_type: 'mortar', aim_instance: 'fallback'}]});
  assert.equal(render().length, 1);
  view.destroy();
  console.log('Deployment flash: delayed delivery, layer order, both teams, expiry, deduplication, replacement and reset passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });
