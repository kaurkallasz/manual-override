/* Exercise the actual player range updater and mobile projection without hardware. */
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const html=fs.readFileSync('shared/robot_controls/controller.html','utf8');
const updater=html.slice(html.indexOf('function applyRelayZLimits(value)'),html.indexOf('\nasync function init()',html.indexOf('function applyRelayZLimits(value)')));
const labels=[{},{}],slider={value:'95',parentElement:{querySelectorAll:()=>labels}},number={value:'95'},hint={};
let paused=0,rendered=0;
const ctx={ws:{z:[-150,230]},sliderEls:{z:slider},numEls:{z:number},gameRadiusMin:220,gameRadiusMax:439,AUTO_PP_BASE_SAFE_RADIUS:220,
  pauseUserMoves(){paused++;},renderCraneControl(axis){assert.equal(axis,'z');rendered++;},document:{getElementById:()=>hint}};
vm.createContext(ctx);vm.runInContext(updater,ctx);
const value={contract:'hhh.relay.z-limits',version:1,status:'ready',minimum:-102,maximum:80};
ctx.applyRelayZLimits(value);
assert.deepEqual(Array.from(ctx.ws.z),[-102,80]);assert.equal(slider.max,80);assert.equal(number.max,80);
assert.equal(slider.value,'95','Changing the range must not replace the actual/selected height with a new goal');
assert.equal(labels[1].textContent,'80 mm');assert.match(hint.textContent,/safe reach ring 220-439 mm; Z -102-80 mm/);
ctx.applyRelayZLimits({...value,maximum:65});assert.equal(slider.max,65);assert.equal(paused,2);
for(const invalid of [{...value,version:true},{...value,maximum:NaN},{...value,status:'unavailable'},{...value,minimum:90}])ctx.applyRelayZLimits(invalid);
assert.equal(slider.max,65);assert.equal(paused,2);assert.equal(rendered,2);
console.log('PASS player height range follows valid relay limits, updates labels and cancels queued input without issuing a goal');
