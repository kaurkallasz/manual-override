// Run: node tests/atom_buff_renderer.cjs
const assert = require('node:assert/strict');
let now = 1000;
let strokes = [], labels = [], clips = [], arcs = [], fills = [];
global.performance = {now: () => now};
global.requestAnimationFrame = () => 1;
global.cancelAnimationFrame = () => {};
function canvas() {
  const context = new Proxy({
    measureText() { return {width: 0}; },
    stroke() { strokes.push(this.strokeStyle); },
    fillText(text) { labels.push(text); },
    clip(rule) { clips.push(rule); },
    arc(x, y, radius) { arcs.push({color: this.strokeStyle, radius}); },
    fillRect(x, y, width, height) { fills.push({color: this.fillStyle, x, y, width, height}); },
    createRadialGradient() { return {addColorStop() {}}; },
  }, {get: (target, key) => key in target ? target[key] : () => {}});
  return {style: {}, getContext: () => context};
}
global.document = {hidden: false, createElement: canvas, addEventListener() {}, removeEventListener() {}};
global.Image = class {
  constructor() {this.width = this.naturalWidth = 8064; this.height = this.naturalHeight = 112;}
  set src(value) {this.url=value;queueMicrotask(() => this.onload());}
  get src() {return this.url;}
};
require('../sandboxes/gamemaster/prototypes/laser-tag-y/tower-defence-view.js');
const metric = TowerDefenceView.geometry.towerHealthBarMetrics;
const tower = {placement_id: 'one', socket_id: 'one', x: 400, y: 400, atom_tag_id: 103,
  owner: 'purple', tower_type: 'tesla_coil', hp: 150, max_hp: 200,
  atom_buff_state: 'active', atom_health_multiplier: 2, atom_damage_multiplier: 2,
  activation_started_at: 0, targeting: {range: 0}};
assert.deepEqual(metric(tower, 100).barFractions, [1, .5]);
assert.deepEqual(metric({...tower, hp: 50}, 100).barFractions, [.5, 0]);
assert.deepEqual(metric({...tower, hp: 75, max_hp: 100, atom_buff_state: 'inactive'}, 100).barFractions, [.75]);
const view = TowerDefenceView.create({mapCanvas: canvas(), gameCanvas: canvas()});
let state = {run_id: 'test', status: 'ready', phase: 'setup', runtime_time: 100, sim_time: 100,
  level_revision: 1, level: {width: 1696, height: 960, sockets: [], paths: {}},
  presentation: {contract: 'photon.level.assets', version: 1, status: 'ready', base: '/art', revision: 1,
    assets: {'tower/tesla_coil/activation': 'activation.png'}},
  towers: [tower], companions: [], enemies: [], active_enemies: 1000};
function render(patch) {
  if (patch) { state = {...state, ...patch}; view.applyState(state); }
  strokes=[];labels=[];clips=[];arcs=[];fills=[];
  view.renderGame(now);
  return strokes.filter(color => typeof color === 'string' && color.startsWith('rgba(73,255,136,'));
}
const glowArcs = () => arcs.filter(a => typeof a.color === 'string' && a.color.startsWith('rgba(73,255,136,'));
const barRows = () => fills.filter(f => f.color === '#240b10' && f.width === 68 && f.height === 6);
(async () => {
assert.equal(render({}).length, 3, 'persistent green glow on Purple at dense effect quality');
assert.ok(labels.includes('×2'));
assert.ok(clips.includes('evenodd'), 'clip the aura around authored marker keep-outs');
const initial = render();
now += 200;
assert.notDeepEqual(render(), initial, 'pulse advances without snapshots, including setup/paused time');
now += 150000;
assert.equal(render({runtime_time: 250, paused: true}).length, 3, 'not a timed deployment pulse');
const inactive = {...tower, hp: 75, max_hp: 100, atom_buff_state: 'inactive', atom_health_multiplier: 1, atom_damage_multiplier: 1};
const fullGlow = render({towers: [inactive]});
assert.equal(fullGlow.length, 3, 'removal begins the power-down at the previous pulse brightness');
const fullRadius = glowArcs()[0].radius;
assert.ok(!labels.includes('×2'));
assert.equal(barRows().length, 1, 'normal capacity is displayed immediately');
now += 300;
assert.notDeepEqual(render({towers: [inactive]}), fullGlow, 'duplicate snapshots do not restart fading');
assert.ok(glowArcs()[0].radius < fullRadius, 'the halo contracts as it powers down');
now += 301;
assert.equal(render().length, 0, 'power-down finishes without another snapshot');
assert.equal(render({towers: [inactive]}).length, 0, 'completed power-down cannot replay');
render({towers: [tower]});
render({towers: [inactive]});
now += 200;
assert.equal(render({towers: [tower]}).length, 3, 'return cancels power-down');
assert.ok(labels.includes('×2'));
render({towers: [{...tower, atom_buff_state: 'unavailable'}]});
assert.ok(!labels.includes('×2'), 'camera unavailability never retains the bonus bar');
now += 601;
assert.equal(render().length, 0, 'camera loss also fades without inventing a return');
assert.equal(render({towers: [{...tower, atom_buff_state: 'inactive'}]}).length, 0);
render({towers: [tower]});
assert.equal(render({towers: [{...tower, destroyed: true}]}).length, 0);
render({towers: [tower]});
assert.equal(render({run_id: 'next', towers: [inactive]}).length, 0, 'new run clears glow history');
render({towers: [tower]});
assert.equal(render({towers: [{...inactive, aim_instance: 'replacement'}]}).length, 0, 'replacement does not inherit the old glow');
render({towers: [tower]});
assert.equal(render({towers: []}).length, 0);
assert.equal(render({towers: [inactive]}).length, 0, 'removed placements discard their history');
await new Promise(resolve => setImmediate(resolve));
render({towers: [{...tower, activation_started_at: 249, hp: 200}]});
assert.equal(barRows().length, 2, 'both full health rows are visible during the three-second deployment');
assert.ok(labels.includes('×2'));
assert.equal(render({towers: [tower], companions: [{...tower, placement_id: 'child', is_companion: true, x: 550}]}).length, 6);
render({towers: [inactive], companions: [{...inactive, placement_id: 'child', is_companion: true, x: 550}]});
now += 601;
assert.equal(render().length, 0, 'both parent and companion finish powering down');
const applied=[];
const receiver=TowerDefenceView.presentation.snapshotReceiver(state => applied.push(state));
receiver.full(state);
receiver.update({towers: [{...tower, atom_buff_state: 'inactive', atom_health_multiplier: 1, atom_damage_multiplier: 1}]});
assert.equal(applied.at(-1).towers[0].atom_damage_multiplier, 1, 'incremental clearing is authoritative');
view.destroy();
console.log('Atom buff renderer: pulsing, deployment health, power-down, return, companion, reset, marker clipping and SSE clearing passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });
