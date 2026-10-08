// Run: node tests/atom_buff_renderer.cjs
const assert = require('node:assert/strict');
let now = 1000;
let strokes = [], labels = [], clips = [];
global.performance = {now: () => now};
global.requestAnimationFrame = () => 1;
global.cancelAnimationFrame = () => {};
function canvas() {
  const context = new Proxy({
    measureText() { return {width: 0}; },
    stroke() { strokes.push(this.strokeStyle); },
    fillText(text) { labels.push(text); },
    clip(rule) { clips.push(rule); },
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
const state = {run_id: 'test', status: 'ready', phase: 'setup', runtime_time: 100, sim_time: 100,
  level_revision: 1, level: {width: 1696, height: 960, sockets: [], paths: {}},
  towers: [tower], companions: [], enemies: [], active_enemies: 1000};
function render(patch={}) {
  view.applyState({...state, ...patch});
  strokes=[];labels=[];clips=[];
  view.renderGame(now);
  return strokes.filter(color => typeof color === 'string' && color.startsWith('rgba(73,255,136,'));
}
assert.equal(render().length, 3, 'persistent green glow on Purple at dense effect quality');
assert.ok(labels.includes('×2'));
assert.ok(clips.includes('evenodd'), 'clip the aura around authored marker keep-outs');
now += 150000;
assert.equal(render({runtime_time: 250}).length, 3, 'not a timed deployment pulse');
assert.equal(render({towers: [{...tower, atom_buff_state: 'unavailable'}]}).length, 0);
assert.ok(!labels.includes('×2'));
assert.equal(render({towers: [{...tower, atom_buff_state: 'inactive'}]}).length, 0);
assert.equal(render({towers: [{...tower, destroyed: true}]}).length, 0);
const applied=[];
const receiver=TowerDefenceView.presentation.snapshotReceiver(state => applied.push(state));
receiver.full(state);
receiver.update({towers: [{...tower, atom_buff_state: 'inactive', atom_health_multiplier: 1, atom_damage_multiplier: 1}]});
assert.equal(applied.at(-1).towers[0].atom_damage_multiplier, 1, 'incremental clearing is authoritative');
view.destroy();
console.log('Atom buff renderer: health segments, both bonus states, dense-quality green halo, marker clipping and SSE clearing passed.');
