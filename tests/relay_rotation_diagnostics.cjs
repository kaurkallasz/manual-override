// Run the real operator renderer without a server or robot commands.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const html = fs.readFileSync(path.join(__dirname, '../sandboxes/gamemaster/prototypes/dobot-mg400-relay/controller.html'), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1].replace(/\ninit\(\);\s*$/, '\n');
const elements = new Map();
const element = () => ({textContent:'', className:'', style:{}, addEventListener(){}});
const document = {getElementById(id) {if (!elements.has(id)) elements.set(id, element()); return elements.get(id);}, addEventListener(){}};
let now = 0, tick;
const context = vm.createContext({document, window:{addEventListener(){}}, location:{pathname:'/p/dobot-mg400-relay/'},
  performance:{now:()=>now}, setInterval:fn=>{tick=fn;}, fetch:()=>{throw Error('Monitoring must not issue commands');}});
vm.runInContext(script, context);
const card = () => Object.fromEntries(['connPill','connText','sMode','sEnabled','sFollower','sPump','sJoints','sPose',
  'sPresent','sLease','sServoErr','stallWarn','sRotation','sRotationStatus'].map(key=>[key,element()]));
context.fixtureCards = {purple:card(), green:card()};
vm.runInContext('Object.assign(cards, fixtureCards)', context);
const arm = (angle, extra={}) => ({connected:true, feedback_ok:true, feedback_age:.01,
  joints:[90,19,59,angle], pose:[250,10,60,47.5], enabled:false, ...extra});
const send = (purple, green=arm(-250)) => {
  context.fixtureState = {arms:{purple, green}};
  vm.runInContext('applyState(fixtureState)', context);
};
const p = context.fixtureCards.purple, g = context.fixtureCards.green;
send(arm(1577.5, {error:true, alarm_ids:[70], fault_kind:'joint4_positive_limit'}));
assert.equal(p.sRotation.textContent, '1577.5°');
assert.equal(p.sRotation.className, 'sRotation outside');
assert.match(p.stallWarn.textContent, /J4 POSITIVE ROTATION LIMIT \(70\)/);
assert.match(p.stallWarn.textContent, /1217.5° above/);
assert.match(p.stallWarn.textContent, /decrease/);
assert.match(p.stallWarn.textContent, /Keep the robot disabled/);
assert.equal(p.stallWarn.style.color, 'var(--err)');
assert.equal(g.sRotation.textContent, '-250.0°');
assert.equal(g.sRotation.className, 'sRotation inside');
assert.equal(g.stallWarn.style.display, 'none');

// In-range color cannot erase a latched alarm, including exactly at a limit.
for (const angle of [-360, 0, 300, 360]) {
  send(arm(angle, {error:true, alarm_ids:[70], fault_kind:'joint4_positive_limit'}));
  assert.equal(p.sRotation.className, 'sRotation inside');
  assert.equal(p.stallWarn.style.display, 'block');
  assert.match(p.stallWarn.textContent, /still reports a limit alarm/);
}
send(arm(-400, {alarm_ids:[71], fault_kind:'joint4_negative_limit', enabled:true}));
assert.match(p.stallWarn.textContent, /40.0° below −360°/);
assert.match(p.stallWarn.textContent, /increase/);
assert.match(p.stallWarn.textContent, /do not turn the holder by hand/);
send(arm(688.6));
assert.match(p.stallWarn.textContent, /J4 ROTATION OUT OF RANGE/);
assert.match(p.stallWarn.textContent, /328.6° above/);

for (const [kind, text] of [['emergency_lock', 'EMERGENCY LOCK'], ['collision', 'COLLISION SAFETY STOP']]) {
  send(arm(688.6, {fault_kind:kind, alarm_ids:[70]}));
  assert.ok(p.stallWarn.textContent.indexOf(text) < p.stallWarn.textContent.indexOf('J4 POSITIVE'));
}
send(arm(300, {fault_kind:'workspace_limit', alarm_ids:[17]}));
assert.match(p.stallWarn.textContent, /USABLE-AREA LIMIT STOP/);

for (const extra of [{connected:false}, {feedback_ok:false}, {feedback_ok:undefined},
  ...[undefined,null,true,'0.01',-.1,.51,NaN,Infinity].map(feedback_age=>({feedback_age}))]) {
  send(arm(1577.5, {alarm_ids:[70], ...extra}));
  assert.equal(p.sRotation.textContent, '—');
  assert.equal(p.sRotation.className, 'sRotation');
  assert.equal(p.sJoints.textContent, '—');
  assert.doesNotMatch(p.stallWarn.textContent, /1577|decrease/);
}
for (const angle of [null, '1577.5', NaN, Infinity]) {
  send(arm(angle));
  assert.equal(p.sRotation.textContent, '—');
}
send(arm(1577.5, {alarm_ids:[70]}));
now = 600; tick();
assert.equal(p.sRotation.textContent, '—');
assert.match(p.stallWarn.textContent, /Current angle unavailable/);
send(arm(250));
assert.equal(p.sRotation.textContent, '250.0°');
assert.equal(p.stallWarn.style.display, 'none');
assert.equal(p.sRotation.className, 'sRotation inside');
console.log('J4 diagnostics: complete turns, both limits, safety priority, latched alarms and feedback expiry passed.');
