const assert = require('node:assert/strict');
require('../sandboxes/gamemaster/prototypes/laser-tag-y/tower-defence-view.js');
const api = global.TowerDefenceView;

function fixture(count = 0) {
  let now = 0, callback, draws = 0, drawCost = 0;
  const reports = [], labels = [], listeners = new Map();
  global.performance = {now: () => now};
  global.requestAnimationFrame = fn => {callback = fn; return 1;};
  global.cancelAnimationFrame = () => {callback = null;};
  const context = new Proxy({
    clearRect() {draws++; now += drawCost;},
    fillText(text) {labels.push(text);},
    measureText: () => ({width: 10}),
    createRadialGradient: () => ({addColorStop() {}}),
    createLinearGradient: () => ({addColorStop() {}}),
  }, {get: (target, key) => key in target ? target[key] : () => {}});
  const canvas = () => ({style: {}, getContext: () => context});
  global.document = {
    hidden: false, createElement: canvas,
    addEventListener: (name, fn) => listeners.set(name, fn),
    removeEventListener: name => listeners.delete(name),
  };
  const view = api.create({mapCanvas: canvas(), gameCanvas: canvas(), onPerformance: value => reports.push(value)});
  const state = {
    phase: 'running', sim_time: 10, runtime_time: 10, paused: false,
    active_enemies: count, enemies: [], towers: [], level_revision: 1,
    level: {width: 1696, height: 960, sockets: [], paths: {}},
  };
  view.applyState(state);
  return {
    view, state, reports, labels,
    get draws() {return draws;},
    set cost(value) {drawCost = value;},
    tick(at) {now = at; callback(at);},
  };
}

(async () => {
  for (const refresh of [60, 120]) for (const count of [0, 400, 800, 1000]) {
    const f = fixture(count);
    await new Promise(resolve => setImmediate(resolve));
    const initial = f.draws;
    for (let frame = 1; frame <= refresh * 10; frame++) f.tick(frame * 1000 / refresh);
    const fps = (f.draws - initial) / 10;
    assert.ok(fps >= 59.9 && fps <= 60.1, `${refresh} Hz, ${count} enemies: ${fps} FPS`);
    console.log(`${refresh} Hz / ${count} enemies: ${fps.toFixed(1)} scheduled FPS`);
    f.view.destroy();
  }
  const f = fixture();
  await new Promise(resolve => setImmediate(resolve));
  const before = f.draws;
  f.view.selectTower('a'); f.view.previewTowerAim('a', 45, 0.5);
  f.view.clearTowerAimPreview('a'); f.view.applyState(f.state);
  assert.equal(f.draws, before, 'input and SSE callbacks coalesce into the animation frame');
  f.tick(20);
  assert.equal(f.draws, before + 1);
  f.tick(10000);
  assert.equal(f.draws, before + 2, 'long gaps draw once, with no catch-up burst');
  f.view.destroy();

  const adaptive = fixture();
  await new Promise(resolve => setImmediate(resolve));
  adaptive.cost = 25;
  for (let frame = 1; frame <= 90; frame++) adaptive.tick(frame * 1000 / 60);
  assert.equal(adaptive.reports.at(-1).quality, 'dense', 'slow effects reduce detail even with few enemies');
  adaptive.cost = 0;
  for (let frame = 91; frame <= 840; frame++) adaptive.tick(frame * 1000 / 60);
  assert.equal(adaptive.reports.at(-1).quality, 'full', 'sustained headroom restores detail gradually');
  adaptive.view.destroy();

  const jitter = fixture(1000);
  await new Promise(resolve => setImmediate(resolve));
  const jitterInitial = jitter.draws;
  for (let frame = 1; frame <= 600; frame++) jitter.tick(frame * 1000 / 60 + Math.sin(frame) * .2);
  assert.ok(jitter.draws - jitterInitial >= 598, 'refresh jitter must not reintroduce skipped-frame throttling');
  jitter.view.destroy();

  const rows = fixture();
  rows.state.row_barrier_geometry = [{row_id:'outer_top',ax:0,ay:160,bx:1440,by:160,opening_side:'right'}];
  rows.state.row_barriers = [{row_id:'outer_top',active_count:3,powered:true,changed_at:10}];
  rows.view.applyState(rows.state);
  await new Promise(resolve => setImmediate(resolve));
  rows.tick(20);
  assert.ok(rows.labels.includes('ROW 3/3'), 'powered row is rendered');
  rows.state.row_barriers = [{row_id:'outer_top',active_count:2,powered:false,changed_at:10}];
  rows.view.applyState(rows.state); rows.tick(40);
  assert.ok(rows.labels.includes('ROW 2/3 · BROKEN'), 'turret loss is visible');
  rows.view.destroy();

  const received = [];
  const receiver = api.presentation.snapshotReceiver(value => received.push(value));
  assert.throws(() => receiver.update({wave: 2}), /complete snapshot/);
  receiver.full({level: {name: 'one'}, settings: {brute_size_multiplier: 2}, row_barrier_geometry: [{row_id: 'outer_top'}], wave: 1, temporary: true});
  receiver.update({wave: 2});
  assert.equal(received.at(-1).level.name, 'one');
  assert.equal(received.at(-1).settings.brute_size_multiplier, 2);
  assert.equal(received.at(-1).row_barrier_geometry[0].row_id, 'outer_top', 'row geometry survives incremental state updates');
  assert.ok(!Object.hasOwn(received.at(-1), 'temporary'), 'only declared static fields carry forward');
  receiver.full({level: null, settings: null, status: 'unavailable'});
  receiver.update({status: 'unavailable'});
  assert.equal(received.at(-1).level, null, 'reconnect/unavailable snapshots clear stale state');
})().catch(error => {console.error(error); process.exitCode = 1;});
