// Deterministic snapshots and browser time; no server, network or robot commands.
const assert = require('node:assert/strict');
require('../sandboxes/gamemaster/prototypes/laser-tag-y/tower-defence-view.js');
const create = global.TowerDefenceView.presentation.enemyMotion;
const near = (actual, expected, tolerance = 1e-6) =>
  assert.ok(Math.abs(actual - expected) <= tolerance, `${actual} != ${expected}`);
const enemy = (x, y = 0, extra = {}) => ({id:1, x, y, vx:100, vy:0, facing_x:1, facing_y:0, hp:100, ...extra});
const snapshot = (t, enemies = [enemy(t * 100)], extra = {}) => ({
  run_id:'one', level_revision:1, phase:'running', paused:false,
  sim_time:t, server_time:1000 + t, enemies, kills:0, ...extra,
});
const guideContract = {contract:'photon.enemy-motion',version:1,horizon_s:1.2};
function guided(t, unit, extra = {}) {
  return snapshot(t, [unit], {enemy_motion:guideContract,row_topology_revision:0,...extra});
}
function receive(motion, state, at) { assert.equal(motion.push(state, at), true); return state; }
function sample(motion, state, at) { return motion.sample(state.enemies, at).get(1); }

// A 900 ms outage must carry the body around a turn at its known speed,
// rather than braking after 150 ms or continuing straight through the wall.
const road = create({delay:0});
let roadState = receive(road, guided(0, enemy(0,0,{motion:{mode:'road',revision:0,speed:100,points:[[40,0],[40,200]]}})),0);
near(sample(road,roadState,300).x,30);
near(sample(road,roadState,900).x,40);
near(sample(road,roadState,900).y,50);
near(sample(road,roadState,1000).y,60);
near(sample(road,roadState,1200).y,80);
near(sample(road,roadState,1400).y,90);
near(sample(road,roadState,10000).y,90);
const beforeCorrection = sample(road,roadState,10000);
roadState = receive(road,guided(.9,enemy(40,45,{vx:0,vy:100,motion:{mode:'road',revision:0,speed:100,points:[[40,200]]}})),10000);
near(sample(road,roadState,10000).x,beforeCorrection.x);
near(sample(road,roadState,10000).y,beforeCorrection.y);
roadState = receive(road,guided(1,enemy(40,55,{motion:{mode:'hold',revision:1,speed:0,points:[]}}),{row_topology_revision:1}),10100);
near(sample(road,roadState,11000).y,55);
roadState = receive(road,snapshot(1.1,[],{enemy_motion:guideContract,row_topology_revision:1,kills:1}),11100);
assert.equal(road.sample(roadState.enemies,11100).size,0,'prediction cannot resurrect a death');

const badGuide = create({delay:0});
let badState = receive(badGuide,guided(0,enemy(7,0,{motion:{mode:'road',revision:0,speed:100,points:[[Infinity,0]]}})),0);
near(sample(badGuide,badState,900).x,7);
const orbit = create({delay:0});
const orbitState = receive(orbit,guided(0,enemy(60,-30,{attacking:true,motion:{mode:'orbit',revision:0,speed:100,points:[[60,30],[30,60],[-30,60]]}})),0);
near(sample(orbit,orbitState,900).x,60-30/Math.sqrt(2));
near(sample(orbit,orbitState,900).y,30+30/Math.sqrt(2));
assert.ok(sample(orbit,orbitState,1200).y===60,'attacking units keep orbiting rather than freezing');

// Regular packets move continuously between authoritative positions. The
// initial 300 ms buffer fills once; arrivals do not reset movement each frame.
const steady = create();
let state;
for (let i = 0; i <= 20; i++) state = receive(steady, snapshot(i * .15), i * 150);
near(sample(steady, state, 3000).x, 270);
near(sample(steady, state, 3050).x, 275);
near(sample(steady, state, 3100).x, 280);
assert.equal(state.enemies[0].x, 300, 'presentation never mutates server coordinates');

// Delayed/batched delivery still uses simulation timestamps, not packet count.
const jitter = create();
receive(jitter, snapshot(0), 0);
receive(jitter, snapshot(.15), 150);
receive(jitter, snapshot(.3), 430);
receive(jitter, snapshot(.45), 450);
state = receive(jitter, snapshot(.6), 600);
near(sample(jitter, state, 600).x, 30);
near(sample(jitter, state, 650).x, 35);
const before = sample(jitter, state, 1050);
state = receive(jitter, snapshot(.75, [enemy(70, 20, {vx:0, vy:100, facing_x:0, facing_y:1})]), 1050);
const after = sample(jitter, state, 1050);
near(after.x, before.x); near(after.y, before.y);
const settled = sample(jitter, state, 3000);
near(settled.x, 70, .01); near(settled.y, 52.5, .01);
near(sample(jitter, state, 60000).y, settled.y, .01);

// A gap uses bounded, decelerating prediction, not a 140 ms freeze or a
// three-second straight-line guess through corners/walls.
const outage = create({delay:0});
state = receive(outage, snapshot(0), 0);
near(sample(outage, state, 100).x, 10);
near(sample(outage, state, 150).x, 15, 1e-6);
assert.ok(sample(outage, state, 250).x > 15);
near(sample(outage, state, 500).x, 32.5);
near(sample(outage, state, 10000).x, 32.5);
outage.setConnected(false, 10000);
near(sample(outage, state, 10001).x, 32.5);
outage.setConnected(true, 10000);
const stopped = sample(outage, state, 10000);
state = receive(outage, snapshot(1, [enemy(45)]), 10000);
near(sample(outage, state, 10000).x, stopped.x, 1e-6);

// Full three-second delayed playback is available explicitly. Keep enough
// history to bracket it, including when a stream delivers a batch at once.
const delayed = create({delay:3});
for (let i = 0; i <= 100; i++) state = receive(delayed, snapshot(i * .1), i * 100);
near(sample(delayed, state, 10000).x, 700, .01);
near(sample(delayed, state, 10050).x, 705, .01);

// Adaptive playback absorbs repeated jitter without a sudden buffer jump.
// Run frame-by-frame so changing the delay cannot hide in a packet-only test.
const adaptive = create();
let packet = 0, adaptiveState, lastBuffer = 300, previousX = null;
for (let at = 0; at <= 10000; at += 10) {
  while (Math.ceil(packet / 4) * 600 <= at) {
    adaptiveState = receive(adaptive, snapshot(packet * .15), at); packet++;
  }
  const p = sample(adaptive, adaptiveState, at);
  const stats = adaptive.diagnostics(at);
  assert.ok(stats.bufferMs >= 250 && stats.bufferMs <= 450);
  assert.ok(Math.abs(stats.bufferMs - lastBuffer) <= .401, 'buffer slews by at most 40 ms per second');
  assert.ok(Number.isFinite(p.x));
  if (previousX !== null) assert.ok(Math.abs(p.x - previousX) < 4, 'no packet/buffer position jumps');
  lastBuffer = stats.bufferMs; previousX = p.x;
}
assert.ok(lastBuffer > 400, 'repeated delivery jitter expands the buffer');
let at = 10010;
// Restore evenly delivered 100 ms updates; the buffer should recover slowly.
let nextPacketAt = at;
let simulationTime = adaptiveState.sim_time;
for (; at <= 30000; at += 10) {
  if (at >= nextPacketAt) {
    simulationTime += .1;
    adaptiveState = receive(adaptive, snapshot(simulationTime), at);
    nextPacketAt += 100;
  }
  sample(adaptive, adaptiveState, at);
  const stats = adaptive.diagnostics(at);
  assert.ok(Math.abs(stats.bufferMs - lastBuffer) <= .401);
  lastBuffer = stats.bufferMs;
}
assert.ok(lastBuffer < 300 && lastBuffer >= 250, 'stable delivery gradually reduces added delay');

// Diagnostics distinguish an empty prediction buffer from a slow redraw loop.
const metrics = create({delay:0});
state = receive(metrics, snapshot(0), 0);
sample(metrics, state, 0); sample(metrics, state, 100);
let report = metrics.diagnostics(100);
near(report.predictionPercent, 50); near(report.updateAgeMs, 100);
assert.equal(report.bufferMs, 0);
for (let i = 1; i <= 20; i++) state = receive(metrics, snapshot(i * .15), i * 150);
report = metrics.diagnostics(3000);
near(report.updateHz, 1 / .15); near(report.updateAgeMs, 0);
report = metrics.diagnostics(9000);
assert.equal(report.updateHz, 0); assert.equal(report.updateAgeMs, 6000);
assert.equal(report.predictionPercent, 0, 'report resets the prediction measurement window');

// Curved interpolation uses both endpoint velocities and does not overshoot.
// Facing crosses the +/-180 degree boundary by the shortest route.
const turn = create({delay:1});
receive(turn, snapshot(0, [enemy(0, 0, {vx:10, facing_x:-1, facing_y:.01})]), 0);
state = receive(turn, snapshot(1, [enemy(10, 10, {vx:0, vy:10, facing_x:-1, facing_y:-.01})]), 1000);
const bend = sample(turn, state, 1500);
assert.ok(bend.x > 5 && bend.y < 5, 'follow endpoint tangents, not the diagonal chord');
assert.ok(bend.facing_x < -.99, 'do not turn through 360 degrees');
for (let at = 1000; at <= 2000; at += 10) {
  const p = sample(turn, state, at);
  assert.ok(p.x >= 0 && p.x <= 10 && p.y >= 0 && p.y <= 10);
}
const reversing = create({delay:1});
receive(reversing, snapshot(0, [enemy(0, 0, {vx:-1000})]), 0);
state = receive(reversing, snapshot(1, [enemy(10, 0, {vx:-1000})]), 1000);
for (let at = 1000; at <= 2000; at += 10) {
  const p = sample(reversing, state, at);
  assert.ok(p.x >= 0 && p.x <= 10, 'reversal tangents cannot overshoot');
}

// Damage, deaths and scores come from the newest snapshot, even during delay.
state = receive(steady, snapshot(3.15, [enemy(315, 0, {hp:4})], {kills:5}), 3150);
assert.equal(sample(steady, state, 3150).hp, 4);
assert.equal(state.kills, 5);
state = receive(steady, snapshot(3.3, [], {kills:6}), 3300);
assert.equal(steady.sample(state.enemies, 3300).size, 0, 'no history ghosts after death');
assert.equal(steady.push(snapshot(3.2), 3400), false, 'stale packet cannot revive dead enemies');
state = receive(steady, snapshot(3.45, [enemy(345)]), 3450);
near(sample(steady, state, 3450).x, 345, .01, 'reused IDs have fresh history');

// Pause and run/map changes discard old trajectories immediately.
state = receive(steady, snapshot(3.6, [enemy(360)], {paused:true}), 3600);
near(sample(steady, state, 20000).x, 360);
state = receive(steady, snapshot(3.6, [enemy(360)], {server_time:1020}), 20000);
near(sample(steady, state, 20000).x, 360);
state = receive(steady, snapshot(0, [enemy(900)], {run_id:'two', server_time:1021}), 21000);
near(sample(steady, state, 21000).x, 900);
state = receive(steady, snapshot(1, [enemy(50)], {run_id:'two', level_revision:2, server_time:1022}), 22000);
near(sample(steady, state, 22000).x, 50);
state = receive(steady, snapshot(1.1, [enemy(900)], {run_id:'two', level_revision:2, server_time:1023}), 22100);
near(sample(steady, state, 22100).x, 900, .01);
steady.clear();
near(sample(steady, snapshot(0, [enemy(7)]), 30000).x, 7);

// Exercise the real Canvas integration: visuals interpolate but the supplied
// snapshot and combat facts remain untouched. Deletion must remove the body.
let now = 0;
const arcs = [];
global.performance = {now:() => now};
global.requestAnimationFrame = () => 1;
global.cancelAnimationFrame = () => {};
const context = new Proxy({arc:(...args) => arcs.push(args),
  measureText:() => ({width:10}), createLinearGradient:() => ({addColorStop(){}}),
  createRadialGradient:() => ({addColorStop(){}}),
}, {get:(target, key) => key in target ? target[key] : () => {}});
const canvas = () => ({style:{}, getContext:() => context});
global.document = {createElement:canvas};
const view = global.TowerDefenceView.create({mapCanvas:canvas(), gameCanvas:canvas()});
view.setFeedConnected(true);
for (let i = 0; i <= 10; i++) {
  now = i * 150;
  view.applyState(snapshot(i * .15, [enemy(i * 15, 123)], {
    level:{width:1696, height:960, paths:{}, sockets:[]}, towers:[],
  }));
}
arcs.length = 0;
view.renderGame(1550);
assert.ok(arcs.some(([x, y]) => Math.abs(x - 125) < .01 && y === 123), 'Canvas uses interpolated positions');
now = 1650;
view.applyState(snapshot(1.65, [], {towers:[]}));
arcs.length = 0;
view.renderGame(now);
assert.ok(!arcs.some(([, y]) => y === 123), 'Canvas removes dead enemies immediately');
view.destroy();
console.log('Timestamped interpolation, turns, prediction, correction, authority and Canvas checks passed.');
