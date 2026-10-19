// Run only against tests/mobile_ltz_fixture.py on port 8137 (no real hardware).
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 try{
  const context=await browser.newContext({viewport:{width:1440,height:1050}}),errors=[];
  context.on('page',page=>page.on('pageerror',e=>errors.push(e.message)));
  await context.addInitScript(()=>{try{localStorage.setItem('mobile-ltz:stopped','yes');localStorage.setItem('mobile-ltz:purple:stopped','yes');}catch{}});
  const base='http://127.0.0.1:8137',api=base+'/s/gamemaster/p/mobile-ltz-api/api/delay';
  await context.request.post(api,{data:{action:'stop'}});
  const monitor=await context.newPage();await monitor.goto(base+'/s/gamemaster/p/mobile-ltz-api/delay-analysis');
  await monitor.getByRole('button',{name:'Start recording',exact:true}).waitFor();
  await monitor.waitForFunction(()=>!document.getElementById('start').disabled);
  const initial=await (await context.request.get(api)).json();
  assert.ok((await monitor.locator('#storage').textContent()).includes(`/ ${initial.limits.file_bytes/1048576} MiB`));
  assert.equal(await monitor.locator('#seconds').inputValue(),'0','full game capture defaults to manual stop');
  const player=await context.newPage();let uploads=0,commands=0;
  player.on('request',r=>{if(r.url().includes('/api/diagnostics')&&r.postData()?.includes('delay.analysis'))uploads++;if(r.url().includes('/api/command'))commands++;});
  await player.goto(base+'/s/green/p/mobile-ltz/');
  await player.waitForFunction(()=>!!window.mobileDelay);
  assert.equal(await player.evaluate(()=>window.mobileDelay.active),false);
  assert.equal(uploads,0);
  await monitor.getByRole('button',{name:'Start recording',exact:true}).click();
  await player.waitForFunction(()=>window.mobileDelay.active);
  await monitor.waitForFunction(()=>document.getElementById('operations').textContent.includes('mobile.snapshot'));
  await player.evaluate(()=>{const until=performance.now()+320;while(performance.now()<until){}});
  await monitor.waitForFunction(()=>document.getElementById('operations').textContent.includes('browser.apply'));
  await monitor.waitForFunction(()=>document.getElementById('incidents').children.length>0);
  let data;for(let attempt=0;attempt<30;attempt++){data=await (await context.request.get(api)).json();if(data.operations.some(o=>o.name==='browser.event_loop_lag'&&o.max_ms>150))break;await new Promise(r=>setTimeout(r,200));}
  if(!data.operations.some(o=>o.name==='browser.event_loop_lag'&&o.max_ms>150))console.log(JSON.stringify({capture:data.capture_id,operations:data.operations.filter(o=>o.name.startsWith('browser.')),player:await player.evaluate(()=>({active:mobileDelay.active,queue:mobileDelay.queue.length,dropped:mobileDelay.dropped,hidden:document.hidden}))}));
  assert.ok(data.operations.some(o=>o.name==='browser.event_loop_lag'&&o.max_ms>150));
  assert.ok(data.participants.some(p=>p.source.includes('/browser/')&&p.recording));
  await monitor.getByRole('button',{name:'Mark incident',exact:true}).click();
  await monitor.waitForFunction(()=>document.getElementById('incidents').textContent.includes('Operator marked incident'));
  await context.request.post(base+'/s/gamemaster/p/mobile-ltz-api/api/diagnostics?side=green',{data:{
   version:1,id:'delay-fixture-hold',source:'bridge',event:'cue_motion_held',client_at:Date.now()/1000,
   reason:'Target outside verified region',context:{tag_id:49,board:{status:'partial',pending_fixed_ids:[48],
    verification:{anchor_ids:[40,41,42,43],hull:[[0,0],[1,0],[0,1]]}},servo_error:'Fixture IPC timeout'}}});
  await monitor.waitForFunction(()=>document.getElementById('incidents').textContent.includes('connection.cue_motion_held'));
  await monitor.getByRole('button',{name:/connection.cue_motion_held/}).click();
  await monitor.waitForFunction(()=>document.getElementById('evidence').textContent.includes('anchor_ids'));
  await monitor.screenshot({path:'/tmp/delay-analysis-desktop.png',fullPage:true});
  await monitor.setViewportSize({width:390,height:844});
  assert.ok(await monitor.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await monitor.screenshot({path:'/tmp/delay-analysis-mobile.png',fullPage:true});
  await monitor.getByRole('button',{name:'Stop recording',exact:true}).click();
  await player.waitForFunction(()=>!window.mobileDelay.active&&window.mobileDelay.timer===null&&window.mobileDelay.observer===null);
  await monitor.waitForFunction(()=>document.getElementById('state').textContent==='Recording off');
  await new Promise(r=>setTimeout(r,2200));const after=uploads;
  await new Promise(r=>setTimeout(r,1200));assert.equal(uploads,after,'no periodic uploads after stop');
  const stopped=await (await context.request.get(api)).json();
  assert.ok(stopped.participants.some(p=>p.source.includes('/browser/')&&!p.recording));
  assert.ok(stopped.received>0);assert.equal(stopped.recording,false);
  const exported=await context.request.get(api+'/export');assert.equal(exported.status(),200);assert.ok((await exported.text()).includes('browser.apply'));
  await monitor.reload();await monitor.waitForFunction(()=>document.getElementById('operations').textContent.includes('mobile.snapshot'));
  // UI presentation of real API warning fields is verified independently from
  // recorder storage-limit tests, without filling disk or commanding a robot.
  const warning={...stopped,limits:{...stopped.limits,file_bytes:128*1048576},warnings:['Detailed trace storage is full. Timing summaries continue while recording is on; later incident details are incomplete.'],detail_truncated:true};
  await monitor.route(api,route=>route.fulfill({json:warning}));
  await monitor.route(api+'/events',route=>route.fulfill({contentType:'text/event-stream',body:'data: '+JSON.stringify(warning)+'\n\n'}));
  await monitor.reload();await monitor.locator('#coverageWarning').waitFor({state:'visible'});
  assert.match(await monitor.locator('#coverageWarning').textContent(),/summaries continue/);
  assert.match(await monitor.locator('#storage').textContent(),/\/ 128 MiB/,'budget comes from the active server');
  assert.equal(await monitor.locator('#state').textContent(),'Recording off');
  assert.equal(commands,0);assert.deepEqual(errors,[]);
  console.log(JSON.stringify({records:stopped.received,dropped:stopped.dropped,operations:stopped.operations.length,uploads,commands,errors,offAcknowledged:true}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
