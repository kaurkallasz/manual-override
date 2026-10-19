/* Actual cue presentation/command handlers; no browser or robot connection. */
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('shared/mobile_ltz/mobile.js','utf8');
function context(){
 const nodes=new Map(),commands=[],notices=[],events=[];
 const $=id=>{if(!nodes.has(id))nodes.set(id,{dataset:{},attributes:{},textWrites:0,attributeWrites:0,
  set textContent(value){this.firstChild={textContent:value};this.textWrites++;},get textContent(){return this.firstChild?.textContent||'';},
  setAttribute(name,value){this.attributes[name]=value;this.attributeWrites++;},getAttribute(name){return this.attributes[name]??null;},
  querySelectorAll:()=>[],querySelector:()=>null});return nodes.get(id);};
 const c={$,...{commands,notices,events},state:{status:'ready',phase:'running',paused:false,virtual_play:false,mobile_safety:{status:'ready'},
  mobile_arm:{enabled:true,motion_ready:true,xyz_limits:{z:[-102,80]},cue:{rows:[],status:'idle',index:0,stage:''}}},
  team:'green',teamLabel:'Green',feedReady:true,session:'test',awaitingControlMode:null,controlMode:'cue',controlRevision:1,
  switchBusy:false,cueBusy:false,cuePendingAction:'',cueInputSequence:0,cueDirty:true,cueDraft:[{piece:100,destination:45}],cueNotice:'',cueLogNotice:'',cueLastStatus:'',
  viewport:{rotation:0},cueWaypointRow:{},xyzTarget:{z:20},transitionAllowsControls:()=>true,
  feedback:(text,important)=>notices.push({text,important}),connectionLog:{record:(...args)=>events.push(args)},
  cancelXYZ(){},renderControls(){},command:async(action,data)=>{commands.push({action,data});return {ok:true,arm:{cue:{rows:data.rows}}};}};
 c.available=()=>c.feedReady&&!!c.session&&!c.state.paused&&c.state.mobile_arm?.motion_ready;
 c.cueLocked=()=>['running','paused','waiting'].includes(c.state.mobile_arm?.cue?.status);
 vm.createContext(c);
 vm.runInContext(source.slice(source.indexOf('function cueRowLabel('),source.indexOf('function renderCueRows(')),c);
 vm.runInContext(source.slice(source.indexOf('function cueReadiness()'),source.indexOf('function syncCue(')),c);
 vm.runInContext(source.slice(source.indexOf('async function cueAction('),source.indexOf("$('cueAdd').onclick")),c);
 vm.runInContext(source.slice(source.indexOf("$('cuePlay').onpointerdown"),source.indexOf("$('cueWaypointCancel').onclick")),c);
 return c;
}
test('game running is separate from arm readiness and a persistent cue failure',()=>{
 const c=context();c.cueDirty=false;c.state.mobile_arm.cue={status:'error',index:0,error:'pump receipt rejected',stage:'16 tags ready'};
 c.updateCueControls();
 assert.equal(c.$('cueGameState').textContent,'Game running');assert.equal(c.$('cueArmState').textContent,'Arm ready');
 assert.equal(c.$('cueRunState').textContent,'Cue failed');assert.equal(c.$('cueHint').textContent,'pump receipt rejected');
 assert.equal(c.$('cuePlay').disabled,false,'A failed cue can be retried');
 for(let i=0;i<50;i++)c.updateCueControls();assert.equal(c.notices.length,1);assert.equal(c.notices[0].important,true);
 c.state.mobile_arm.cue={status:'error',stage:'Original controller failure'};c.updateCueControls();
 assert.equal(c.$('cueHint').textContent,'Original controller failure','Old bridges still surface their error stage');
});
test('a camera-map hold explains blocked Play while leaving completed cue editing available',async()=>{
 const c=context();c.state.mobile_arm.cue.status='completed';
 c.state.mobile_cue_targets={status:'unavailable',error:'Checking fixed marker #40, #48 after a conflicting camera detection.'};
 c.updateCueControls();assert(c.$('cuePlay').disabled);assert.equal(c.$('cueAdd').disabled,false);
 assert.match(c.$('cueHint').textContent,/Checking fixed marker #40, #48/);
 assert.match(c.$('cueHint').textContent,/edit targets/);
 await c.cueAction('cue_play');assert.equal(c.commands.length,0);
 c.cueDraft[0].destination=42;c.state.mobile_cue_targets.status='ready';c.cueNotice='';c.updateCueControls();
 assert.equal(c.$('cuePlay').disabled,false);await c.cueAction('cue_play');
 assert.equal(c.commands.at(-1).data.rows[0].destination,42);
});
test('an unrelated disputed edge allows Play while disputed or unverified selected endpoints explain the hold',async()=>{
 const c=context();c.state.mobile_cue_targets={status:'partial',quarantined_tags:[{id:48}]};
 c.updateCueControls();assert.equal(c.$('cuePlay').disabled,false);
 await c.cueAction('cue_play');assert.equal(c.commands.at(-1).action,'cue_play');
 c.cueNotice='';c.cueDraft[0].destination=48;c.updateCueControls();
 assert(c.$('cuePlay').disabled);assert.match(c.$('cueHint').textContent,/#48 is disputed/);
 c.cueDraft[0].destination=45;c.state.mobile_arm.cue.destinations=[{id:45,mapping_ready:false,mapping_error:'Endpoint #45 is outside the verified board region.'}];
 c.updateCueControls();assert(c.$('cuePlay').disabled);assert.match(c.$('cueHint').textContent,/outside the verified board region/);
});
test('disabled Play shows the game/connection/calibration reason without a command',async()=>{
 for(const reason of ['paused','disconnected','calibration','missing-row']){
  const c=context();
  if(reason==='paused')c.state.paused=true;
  if(reason==='disconnected')c.session=null;
  if(reason==='calibration'){c.state.mobile_arm.motion_ready=false;c.state.mobile_arm.motion_error='Green arm connection changed.';}
  if(reason==='missing-row')c.cueDraft[0].destination=null;
  c.updateCueControls();assert(c.$('cuePlay').disabled,reason);
  const expected={paused:/Game paused/,disconnected:/Press Connect/,calibration:/connection changed/, 'missing-row':/every row/}[reason];
  assert.match(c.$('cueHint').textContent,expected);assert.match(c.$('cuePlay').title,expected);
  await c.cueAction('cue_play');assert.equal(c.commands.length,0);assert.match(c.cueNotice,expected);
 }
});

test('a stopped cue keeps the Play text node and attributes through live refreshes, then starts on one click',async()=>{
 const c=context();c.state.mobile_arm.cue.status='stopped';c.cueDraft=[{piece:100,destination:40}];c.updateCueControls();
 const play=c.$('cuePlay'),label=play.firstChild,writes=play.attributeWrites;
 assert.equal(play.disabled,false);assert.equal(c.$('cueRunState').textContent,'Cue stopped');
 play.onpointerdown({button:0});
 for(let i=0;i<100;i++)c.updateCueControls();
 assert.equal(play.firstChild,label,'Camera/arm refreshes must not replace the pressed text node');
 assert.equal(play.attributeWrites,writes);
 await play.onclick();
 assert.deepEqual(c.commands.map(r=>r.action),['cue_set','cue_play']);
 assert.equal(c.commands.at(-1).data.rows[0].destination,40);
 assert.deepEqual(c.events.map(r=>r[1]),['cue_play_pressed','cue_command_activated','cue_command_requested']);
});

test('Play immediately shows Starting while awaiting setup; repeated input is explained without duplicate commands',async()=>{
 const c=context();let finish;
 c.state.mobile_arm.cue={status:'error',error:'Previous error'};c.cueDirty=false;
 c.command=async(action,data)=>{c.commands.push({action,data});if(action==='cue_set')await new Promise(resolve=>finish=resolve);return {arm:{cue:{rows:data.rows}}};};
 const pending=c.$('cuePlay').onclick();
 assert.equal(c.$('cueRunState').textContent,'Cue starting');assert.equal(c.$('cueHint').textContent,'Starting cue…');
 assert.equal(c.$('cuePanel').dataset.failed,'false');assert.equal(c.$('cuePlay').getAttribute('aria-label'),'Starting cue…');
 const label=c.$('cuePlay').firstChild;
 for(let i=0;i<50;i++)c.updateCueControls();
 assert.equal(c.$('cuePlay').firstChild,label);
 await c.cueAction('cue_play');
 assert.deepEqual(c.commands.map(r=>r.action),['cue_set']);
 assert.equal(c.events.filter(r=>r[1]==='cue_command_activated').length,2);
 assert.equal(new Set(c.events.filter(r=>r[1]==='cue_command_activated').map(r=>r[2])).size,2,'Rapid taps have distinct diagnostic reasons');
 assert(c.events.some(r=>r[1]==='cue_command_blocked'&&/Wait for this command/.test(r[2])));
 assert.equal(c.cueNotice,'','A duplicate tap must not leave a stale error after the first start succeeds');
 finish();await pending;assert.equal(c.cueBusy,false);assert.equal(c.cuePendingAction,'');
 assert.deepEqual(c.commands.map(r=>r.action),['cue_set','cue_play']);
});

test('readiness lost between press and click refuses the command and logs the activation',async()=>{
 const c=context();c.updateCueControls();c.$('cuePlay').onpointerdown({button:0});
 c.switchBusy=true;c.updateCueControls();assert(c.$('cuePlay').disabled);
 await c.$('cuePlay').onclick();
 assert.equal(c.commands.length,0);assert.match(c.$('cueHint').textContent,/control method/);
 assert.deepEqual(c.events.map(r=>r[1]),['cue_play_pressed','cue_command_activated','cue_command_blocked']);
 c.$('cuePlay').onpointercancel();assert.equal(c.events.at(-1)[1],'cue_play_cancelled');assert.equal(c.commands.length,0);
});

test('Stop describes manual arm stopping while idle and cue stopping while active',async()=>{
 const c=context();
 for(const status of ['idle','stopped','completed','error','running','waiting','paused']){
  c.state.mobile_arm.cue.status=status;c.updateCueControls();
  const expected=['running','waiting','paused'].includes(status)?'Stop cue':'Stop arm';
  assert.equal(c.$('cueStopLabel').textContent,expected);assert.equal(c.$('cueStop').getAttribute('aria-label'),expected);
  assert.match(c.$('cueStop').title,/halt arm movement and turn the pump off/);assert.equal(c.$('cueStop').disabled,false);
 }
 c.state.mobile_arm.cue.status='stopped';await c.$('cueStop').onclick();assert.deepEqual(c.commands.map(r=>r.action),['cue_stop']);
 c.state.virtual_play=true;c.updateCueControls();assert.doesNotMatch(c.$('cueStop').title,/pump off/,'Virtual cue Stop retains the simulated gripper state');
 c.session=null;c.updateCueControls();assert.equal(c.$('cueStop').disabled,true);
});
test('idle map taps move immediately without submitting or starting the draft cue',async()=>{
 const c=context();await c.cueAction('cue_waypoint',{point:{x:5,y:6}});
 assert.equal(c.commands.length,1);assert.equal(c.commands[0].action,'cue_waypoint');
 assert.equal(c.cueDirty,true);assert.equal(c.state.mobile_arm.cue.status,'idle');
 c.commands.length=0;
 await c.cueAction('cue_play');
 assert.deepEqual(c.commands.map(row=>row.action),['cue_set','cue_play']);
 assert.equal(c.commands[0].data.rows[0].piece,100);assert.equal(c.commands[0].data.rows[0].destination,45);
 assert.equal(c.cueBusy,false);assert.equal(c.cueNotice,'');
 c.state.mobile_arm.cue.status='waiting';c.state.mobile_arm.cue.waiting={message:'Reveal #100. Check the Atom battery.'};
 c.updateCueControls();assert.match(c.$('cueHint').textContent,/battery/);
 await c.cueAction('cue_waypoint',{point:{x:5,y:6}});assert.equal(c.commands.at(-1).action,'cue_waypoint');
});
test('cancelled setup and unexpected startup errors are visible and do not leave controls busy',async()=>{
 const c=context();c.command=async()=>null;
 await c.cueAction('cue_play');assert.match(c.cueNotice,/setup cancelled/);assert.equal(c.cueBusy,false);
 c.cancelXYZ=()=>{throw Error('Cue initialization failed');};
 await c.cueAction('cue_play');assert.equal(c.cueNotice,'Cue initialization failed');assert.equal(c.cueBusy,false);
 assert(c.events.some(row=>row[1]==='cue_command_failed'&&row[2]==='Cue initialization failed'));
});

test('idle clicks need a ready connected arm but no valid cue rows',async()=>{
 const c=context();c.cueDraft=[];await c.cueAction('cue_waypoint',{point:{x:5,y:6}});
 assert.equal(c.commands.length,1);assert.equal(c.commands[0].action,'cue_waypoint');
 c.session=null;await c.cueAction('cue_waypoint',{point:{x:5,y:6}});
 assert.equal(c.commands.length,1);assert.match(c.cueNotice,/Connect/);
});
test('a mismatched cue setup receipt cannot start an older destination',async()=>{
 const c=context();c.command=async(action,data)=>{c.commands.push({action,data});return {ok:true,arm:{cue:{rows:[{piece:100,destination:47}]}}};};
 await c.cueAction('cue_play');assert.deepEqual(c.commands.map(r=>r.action),['cue_set']);
 assert.match(c.cueNotice,/selection was not confirmed/);assert(c.cueDirty);
});
test('a valid server receipt with reordered JSON fields starts on the first click',async()=>{
 const c=context();c.command=async(action,data)=>{c.commands.push({action,data});return {arm:{cue:{rows:data.rows.map(row=>({destination:row.destination,piece:row.piece}))}}};};
 await c.$('cuePlay').onclick();
 assert.deepEqual(c.commands.map(r=>r.action),['cue_set','cue_play']);assert.equal(c.cueNotice,'');assert.equal(c.cueDirty,false);
 c.commands.length=0;c.state.mobile_arm.cue.rows=[{destination:45,piece:100}];
 await c.$('cuePlay').onclick();assert.deepEqual(c.commands.map(r=>r.action),['cue_play'],'Equivalent rows do not need another setup');
 assert.equal(c.cueRowsEqual([{piece:100,destination:45}],null),false);
 assert.equal(c.cueRowsEqual([{piece:100,destination:45}],[{piece:100,destination:'45'}]),false);
});
test('the exact requested rows travel with Play, and a known unreachable source is explained without motion',async()=>{
 const c=context();c.cueDraft=[{piece:100,destination:50}];await c.cueAction('cue_play');
 assert.equal(c.commands.at(-1).data.rows[0].destination,50);assert.match(c.events[0][2],/100 → 50/);
 c.commands.length=0;c.state.mobile_arm.cue.sources=[{id:100,reachable:false,reason:'Target is inside the red Cal 2 exclusion area'}];
 c.updateCueControls();assert(c.$('cuePlay').disabled);assert.match(c.$('cueHint').textContent,/piece #100 cannot be reached/);
 await c.cueAction('cue_play');assert.equal(c.commands.length,0);assert.match(c.cueNotice,/Reposition the piece/);
});

test('Pause and Stop bypass new-motion gates and missing height limits but still need a session',async()=>{
 for(const action of ['cue_pause','cue_stop']){
  const c=context();c.feedReady=false;c.switchBusy=true;c.cueDraft=[];
  c.state.mobile_arm.xyz_limits=null;c.state.mobile_arm.motion_ready=false;c.state.mobile_arm.cue.status='waiting';
  c.updateCueControls();assert.equal(c.$('cuePlay').disabled,false);assert.equal(c.$('cueStop').disabled,false);
  assert.equal(c.$('cuePlay').title,'Pause cue');
  await c.cueAction(action);assert.deepEqual(c.commands.map(x=>x.action),[action]);assert.equal(c.cueNotice,'');
  c.session=null;await c.cueAction(action);assert.equal(c.commands.length,1);
  c.updateCueControls();assert(c.$('cuePlay').disabled);assert(c.$('cueStop').disabled);
 }
});
test('paused camera wait displays Paused, and Resume retains motion readiness checks',async()=>{
 const c=context();c.state.mobile_arm.cue={status:'paused',waiting:{message:'Reveal tag #100'}};
 c.updateCueControls();assert.match(c.$('cueHint').textContent,/Cue paused/);assert.equal(c.$('cuePanel').dataset.recovering,'false');
 c.feedReady=false;await c.cueAction('cue_play');assert.equal(c.commands.length,0);
});

test('a ready cue does not instruct the player to reposition before Play',()=>{
 const c=context();c.updateCueControls();
 assert.equal(c.$('cuePlay').disabled,false);
 assert.match(c.$('cueHint').textContent,/arm moves automatically/);
 c.state.mobile_arm.cue.status='running';c.updateCueControls();
 assert.match(c.$('cueHint').textContent,/optional/);
 assert.doesNotMatch(c.$('cueHint').textContent,/then continue/);
});
test('Clear view rows and current camera rotation travel intact with Play',async()=>{
 const c=context();c.cueDraft.push({action:'clear_view'});c.viewport.rotation=180;
 await c.cueAction('cue_play');
 assert.deepEqual(c.commands.map(r=>r.action),['cue_set','cue_play']);
 assert.equal(c.commands[0].data.rows[1].action,'clear_view');
 assert.equal(c.commands[1].data.view_rotation,180);assert.equal(c.cueNotice,'');
 assert(c.cueRowsEqual([{action:'clear_view'}],[{action:'clear_view'}]));
 assert(!c.cueRowsEqual([{action:'clear_view'}],[{piece:100,destination:40}]));
 c.cueDraft=[{action:'clear_view'}];c.commands.length=0;await c.cueAction('cue_play');
 assert.equal(c.commands.length,0);assert.match(c.cueNotice,/must follow a placement/);
});
test('view rotation cannot reverse Clear view directions during startup, playback, waiting or pause',()=>{
 const c=context();c.controlPointers=new Set();c.mapPointers=new Map();
 c.viewport.setRotation=value=>{c.viewport.rotation=value;};
 c.preference={set(){}};c.syncRotationControl=()=>{};c.syncViewport=()=>{};c.updateXYZ=()=>{};
 vm.runInContext(source.slice(source.indexOf("$('rotateView').onclick="),source.indexOf('const feedbackLines=')),c);
 for(const status of ['running','waiting','paused']){
  c.state.mobile_arm.cue.status=status;c.updateCueControls();assert.equal(c.$('rotateView').disabled,true);
  c.$('rotateView').onclick();assert.equal(c.viewport.rotation,0);
 }
 c.state.mobile_arm.cue.status='idle';c.cueBusy=true;c.updateCueControls();assert.equal(c.$('rotateView').disabled,true);
 c.$('rotateView').onclick();assert.equal(c.viewport.rotation,0);
 c.cueBusy=false;c.state.mobile_arm.cue.status='completed';c.updateCueControls();assert.equal(c.$('rotateView').disabled,false);
 c.$('rotateView').onclick();assert.equal(c.viewport.rotation,180);
});
test('custom Clear view fields are sent and invalid distances block Play',async()=>{
 const c=context();c.cueDraft.push({action:'clear_view',direction:'right',distance_cm:7.5});
 await c.cueAction('cue_play');
 for(const command of c.commands){assert.equal(command.data.rows[1].direction,'right');assert.equal(command.data.rows[1].distance_cm,7.5);}
 for(const distance of [0,51,NaN,'5',null]){
  c.commands.length=0;c.cueDraft[1].distance_cm=distance;await c.cueAction('cue_play');assert.equal(c.commands.length,0);assert.match(c.cueNotice,/0.1 to 50 cm/);
 }
});
