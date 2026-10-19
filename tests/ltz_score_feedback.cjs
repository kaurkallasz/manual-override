const assert=require('node:assert/strict');
const Score=require('../shared/ltz_ui/score-feedback.js');
let now=0,frames=[],animations=0,cancelled=0;
const number={textContent:'',animate(){animations++;return {cancel(){cancelled++;}}}},burst={textContent:'',classList:{toggle(){}}},detail={};
const score=new Score(number,burst,detail,{now:()=>now,raf:fn=>{frames.push(fn);return frames.length},reduced:()=>false});
function state(n,brute=0){return {run_id:'a',kills:n,mobile_progress:{},match_score:{contract:'photon.match-score',version:1,status:'ready',sequence:n,kill_credits:n+9*brute,counts:{brute},reward_enabled:true}};}
score.update(state(0));score.update(state(1));now=100;score.update(state(2,1));assert.equal(frames.length,1);assert.equal(cancelled,1);assert.match(burst.textContent,/\+11.*Large brute/);
now=300;frames.shift()();assert.equal(number.textContent,'11');score.update(state(2,1));assert.equal(animations,2);score.update(state(1));assert.equal(number.textContent,'11');
score.reconnect();score.update(state(30,2));assert.equal(number.textContent,'48');assert.equal(burst.textContent,'');assert.equal(animations,2);
const saved=state(30,2);saved.mobile_progress.latest_result={run_id:'a',stack_bonus:5,total_earned:53};score.update(saved);assert.match(burst.textContent,/bonus \+5/);now=500;frames.shift()();assert.equal(number.textContent,'53');score.update(saved);assert.equal(animations,3);
score.reduced=()=>true;now=2000;score.update(state(40,2));assert.equal(number.textContent,'58');assert.equal(frames.length,0);assert.match(detail.textContent,/40 kills/);
score.update({...state(0),run_id:'b'});assert.equal(number.textContent,'0');assert.equal(burst.textContent,'');
console.log('Score feedback: cumulative bursts, brute accent, stale/duplicate frames, reconnect, bonus and reduced motion pass');

// Both field faces share the exact tween; kills can grow without earning credits.
let fieldNow=0,fieldFrames=[];
const fieldNodes=Array.from({length:4},()=>({textContent:'',style:{setProperty(){}}}));
const [credits,kills,purpleCredits,purpleKills]=fieldNodes;
const field=new Score(credits,null,null,{killNumber:kills,copies:[{number:purpleCredits,killNumber:purpleKills}],
 now:()=>fieldNow,raf:fn=>{fieldFrames.push(fn);return fieldFrames.length},reduced:()=>false});
field.update(state(0));field.update(state(100,10));
assert.equal(fieldFrames.length,1);fieldNow=90;fieldFrames.shift()();
assert.equal(credits.textContent,purpleCredits.textContent);assert.equal(kills.textContent,purpleKills.textContent);
assert(Number(kills.textContent)>0&&Number(kills.textContent)<100);
fieldNow=180;fieldFrames.shift()();assert.equal(kills.textContent,'100');assert.equal(credits.textContent,'190');
const freeKills=state(120);freeKills.match_score.kill_credits=190;
field.update(freeKills);fieldNow=360;fieldFrames.shift()();
assert.equal(kills.textContent,'120');assert.equal(purpleKills.textContent,'120');assert.equal(credits.textContent,'190');
field.update(state(119));assert.equal(kills.textContent,'120');
field.update(state(150,10));field.update({});fieldNow=600;fieldFrames.shift()();
assert(fieldNodes.every(n=>n.textContent==='—'));
field.reconnect();field.update(state(200));assert.deepEqual(fieldNodes.map(n=>n.textContent),['200','200','200','200']);
field.update({...state(0),run_id:'new'});assert(fieldNodes.every(n=>n.textContent==='0'));
console.log('Field score: mirrored animated kills/credits, one frame loop, zero-credit kills, unavailable state and new-run reset pass');
