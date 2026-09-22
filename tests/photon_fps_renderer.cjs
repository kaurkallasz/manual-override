// Measure completed draws in the real renderer with a deterministic browser clock.
const assert = require('node:assert/strict');
let now = 0, scheduled = null;
const listeners = new Map(), samples = [], diagnostics = [];
global.performance = {now: () => now};
global.requestAnimationFrame = callback => { scheduled = callback; return 1; };
global.cancelAnimationFrame = () => { scheduled = null; };
const context = new Proxy({
  measureText: () => ({width: 10}),
  createRadialGradient: () => ({addColorStop() {}}),
  createLinearGradient: () => ({addColorStop() {}}),
}, {get: (target, key) => key in target ? target[key] : () => {}});
const canvas = () => ({style: {}, getContext: () => context});
global.document = {
  hidden: false, createElement: canvas,
  addEventListener: (event, callback) => listeners.set(event, callback),
  removeEventListener: (event, callback) => {
    assert.equal(listeners.get(event), callback);
    listeners.delete(event);
  },
};
require('../sandboxes/gamemaster/prototypes/laser-tag-y/tower-defence-view.js');
const view = global.TowerDefenceView.create({
  mapCanvas: canvas(), gameCanvas: canvas(), onFps: fps => samples.push(fps),
  onDiagnostics: value => diagnostics.push(value),
});
function tick(ms) {
  now += ms;
  const callback = scheduled;
  scheduled = null;
  callback(now);
}
function visibility(hidden) {
  document.hidden = hidden;
  listeners.get('visibilitychange')();
}
(async () => {
  tick(1000);
  assert.equal(samples.at(-1), 0, 'no playfield must not report animation callbacks as FPS');
  view.applyState({
    phase: 'setup', enemies: [], towers: [], core_hp: 100, core_max_hp: 100,
    level_revision: 1, level: {width: 1696, height: 960, sockets: [], paths: {}},
  });
  await new Promise(resolve => setImmediate(resolve));
  visibility(false);
  for (let i = 0; i < 9; i++) tick(100);
  assert.equal(samples.at(-1), null, 'wait for a full second before showing FPS');
  tick(100);
  assert.equal(samples.at(-1), 10, 'slow rendering reports measured FPS, not the 60 FPS target');
  assert.equal(diagnostics.at(-1).peakFrameMs, 100);
  assert.ok(diagnostics.at(-1).frameSpikes >= 9, 'report stutters hidden by an average FPS number');
  const count = samples.length;
  for (let i = 0; i < 100; i++) tick(10);
  assert.equal(samples.length, count + 1, 'publish once per second');
  assert.equal(samples.at(-1), 60, '100 callbacks preserve a 60 FPS cadence');
  assert.equal(diagnostics.at(-1).frameSpikes, 0, 'frame spikes reset each reporting window');
  // Direct diagnostic draws must not inflate the presented-frame counter.
  for (let i = 0; i < 3; i++) view.renderGame();
  for (let i = 0; i < 10; i++) tick(100);
  assert.equal(samples.at(-1), 10);
  visibility(true);
  const hiddenCount = samples.length;
  tick(10000);
  assert.equal(samples.length, hiddenCount, 'hidden tabs must not publish stale samples');
  visibility(false);
  assert.equal(samples.at(-1), null);
  assert.equal(diagnostics.at(-1), null, 'background/resume clears stale diagnostics');
  for (let i = 0; i < 10; i++) tick(100);
  assert.equal(samples.at(-1), 10, 'resuming starts a fresh measurement window');
  view.destroy();
  assert.equal(scheduled, null);
  assert.equal(listeners.size, 0, 'teardown removes the visibility listener');

  const warnings = [];
  const oldWarn = console.warn;
  console.warn = (...args) => warnings.push(args);
  const brokenMonitor = global.TowerDefenceView.create({
    mapCanvas: canvas(), gameCanvas: canvas(), onFps() { throw new Error('monitor unavailable'); },
  });
  tick(1000);
  assert.equal(warnings.length, 1);
  assert.equal(typeof scheduled, 'function', 'a broken FPS callback must not stop rendering');
  brokenMonitor.destroy();
  console.warn = oldWarn;
})().catch(error => { console.error(error); process.exitCode = 1; });
