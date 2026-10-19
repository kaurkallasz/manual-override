/* Shared timeline on the real projector/GM pages; isolated fake-hardware fixture. */
const assert=require('node:assert/strict'),fs=require('node:fs');
const {chromium}=require('playwright');
const origin=process.env.TIMELINE_FIXTURE_URL||'http://127.0.0.1:56055';
const output=process.env.TIMELINE_OUTPUT||'/tmp/wave-timeline-views';
if(!/^http:\/\/127\.0\.0\.1:(?!8000(?:\/|$))\d+$/.test(origin))throw Error('Isolated fixture required');
(async()=>{
 fs.mkdirSync(output,{recursive:true});
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'}),checks=[];
 try{
  for(const surface of ['screen','game'])for(const width of [1920,1366]){
   const page=await browser.newPage({viewport:{width,height:width===1920?1080:768}}),errors=[];
   page.on('pageerror',e=>errors.push(e.message));
   await page.addInitScript(()=>{window.EventSource=class{addEventListener(){}close(){}};});
   await page.goto(origin+'/s/gamemaster/p/laser-tag-y/'+surface);
   await page.waitForFunction(()=>!document.querySelector('#waveTimeline').hidden);
   const box=await page.locator('#waveTimeline').boundingBox();
   const field=await page.locator(surface==='screen'?'.stage':'#stage').boundingBox();
   assert(box.x>=0&&box.x+box.width<=width);
   if(surface==='screen')assert(box.y>=field.y&&box.y+box.height<field.y+field.height*.12);
   else assert(box.y+box.height<=field.y);
   const result=await page.evaluate(surface=>{
    const source=structuredClone(surface==='screen'?latestState:ui.state),data=source.wave_timeline;
    const first=data.waves[0],now=first.start_s+first.duration_s/2;
    source.phase='running';source.paused=true;source.server_time=Date.now()/1000;source.run_id='timeline-browser';
    source.journey={...source.journey,phase:'playing'};
    source.kills=624;source.match_score={contract:'photon.match-score',version:1,status:'ready',sequence:624,kill_credits:12480,reward_enabled:true,counts:{}};
    data.time_s=now;first.state='spawning';
    applyState(source);window.timelineFixture=source;
    return {waves:data.waves.length,now,start:first.start_s,duration:first.duration_s,end:data.end_s};
   },surface);
   const timeline=page.locator('#waveTimeline');
   assert.equal(await timeline.locator('.ltzWaveBar').count(),result.waves);
   assert.equal(await timeline.locator('.ltzWaveBar.spawning').count(),1);
   assert.match(await timeline.locator('.ltzWaveClock').textContent(),/PAUSED/);
   const before=await timeline.locator('[data-playhead]').getAttribute('transform');await page.waitForTimeout(300);
   assert.equal(await timeline.locator('[data-playhead]').getAttribute('transform'),before);
   const counterIds=surface==='screen'?['matchKillNumber','purpleKillNumber']:['matchScoreNumber','matchKillNumber'];
   assert.deepEqual(await page.evaluate(ids=>ids.map(id=>getComputedStyle(document.getElementById(id)).fontSize),counterIds),counterIds.map(()=>'40px'));
   assert.equal(await page.locator('#matchScoreLabel,#matchScoreBurst').count(),0);
   assert.deepEqual(await page.locator('#matchScoreHud strong').allTextContents(),surface==='screen'?['624']:['624','12,480']);
   if(surface==='screen'){
    assert.equal(await page.locator('.stage>#purpleScoreHud').count(),1);
    assert.equal(await page.locator('.stage>#matchScoreHud').count(),1);
    assert.deepEqual(await page.locator('#purpleScoreHud strong').allTextContents(),['624']);
    assert.equal(await page.locator('.stage .ltzScoreCredits,#matchScoreNumber,#purpleScoreNumber').count(),0);
    assert.equal(await page.locator('#purpleScoreHud').evaluate(e=>getComputedStyle(e).transform),'matrix(-1, 0, 0, -1, 0, 0)');
    const upper=await page.locator('#purpleScoreHud').boundingBox(),lower=await page.locator('#matchScoreHud').boundingBox();
    assert(Math.abs(upper.y-field.y-8)<1,'Purple counter belongs to the top field edge');
    assert(Math.abs(field.y+field.height-lower.y-lower.height-8)<1,'Green counter belongs to the bottom field edge');
    assert(Math.abs(upper.x+upper.width/2-(box.x+box.width+field.x+field.width)/2)<1,'Purple counter is centered between the wave strip and field edge');
    assert(upper.x>=box.x+box.width+8,'Purple counter stays clear of the wave timeline');
    const mirror=page.locator('#purpleWaveTimeline'),mirrorBox=await mirror.boundingBox();
    assert(Math.abs(lower.x+lower.width/2-(field.x+mirrorBox.x)/2)<1,'Green counter is centered between the field edge and wave strip');
    assert.equal(await mirror.evaluate(e=>getComputedStyle(e).transform),'matrix(-1, 0, 0, -1, 0, 0)');
    assert(Math.abs(field.y+field.height-mirrorBox.y-mirrorBox.height-8)<1,'Purple wave indicator sits at the opposite field edge');
    assert(mirrorBox.x>=lower.x+lower.width+8,'Purple wave indicator stays clear of Green kills');
    assert.deepEqual(await mirror.locator('.ltzWaveLabels span').allTextContents(),await timeline.locator('.ltzWaveLabels span').allTextContents());
    assert.equal(await mirror.locator('[data-playhead]').getAttribute('transform'),before);
   }else{
    assert.equal(await page.locator('#purpleScoreHud,.ltzScoreFace.purple').count(),0);
    assert.equal(await page.locator('#matchScoreHud').evaluate(e=>getComputedStyle(e).position),'fixed');
   }
   const barLayout=await page.evaluate(()=>{
    const track=document.querySelector('.ltzWaveTrack'),bounds=track.getBoundingClientRect();
    const labels=[...document.querySelectorAll('#waveTimeline .ltzWaveLabels span')].map(label=>{
     const box=label.getBoundingClientRect();return {text:label.textContent,size:getComputedStyle(label).fontSize,
      inside:box.left>=bounds.left&&box.right<=bounds.right&&box.top>=bounds.top&&box.bottom<=bounds.bottom,
      clipped:label.scrollWidth>label.clientWidth};
    });
    return {height:+track.getAttribute('height'),bottom:+track.getAttribute('y')+Number(track.getAttribute('height')),
     fillHeight:+document.querySelector('.ltzWaveProgress').getAttribute('height'),labels,
     outsideText:document.querySelectorAll('#waveTimeline svg text').length};
   });
   assert.equal(barLayout.height,48);assert.equal(barLayout.fillHeight,32);assert.equal(barLayout.bottom,56);
   assert.equal(barLayout.outsideText,0);
   for(const label of barLayout.labels){assert.equal(label.size,'22px');assert(label.inside,label.text+' outside bar');assert(!label.clipped,label.text+' clipped');}
   const hud=await page.locator('#matchScoreHud').boundingBox();assert(hud.x>=0&&hud.x+hud.width<=width);
   await page.screenshot({path:`${output}/${surface}-${width}.png`});
   // Digit growth and a saved bonus cannot expand the field counter.
   await page.evaluate(()=>{
    timelineFixture.server_time+=1;timelineFixture.kills=123456;
    timelineFixture.match_score.sequence+=1;timelineFixture.match_score.kill_credits=987654;
    applyState(timelineFixture);
   });
   await page.waitForTimeout(220);
   assert.deepEqual(await page.locator('#matchScoreHud strong').allTextContents(),surface==='screen'?['123,456']:['123,456','987,654']);
   if(surface==='screen')assert.deepEqual(await page.locator('#purpleScoreHud strong').allTextContents(),['123,456']);
   assert.deepEqual(await page.locator('#matchScoreHud').boundingBox(),hud);
   await page.evaluate(()=>{
    timelineFixture.server_time+=1;
    timelineFixture.progress={...timelineFixture.progress,result:{run_id:timelineFixture.run_id,reward_enabled:true,kill_credits:987654,bonus_credits:5000}};
    applyState(timelineFixture);
   });
   await page.waitForTimeout(220);
   assert.deepEqual(await page.locator('#matchScoreHud strong').allTextContents(),surface==='screen'?['123,456']:['123,456','992,654']);
   if(surface==='screen')assert.deepEqual(await page.locator('#purpleScoreHud strong').allTextContents(),['123,456']);
   assert.deepEqual(await page.locator('#matchScoreHud').boundingBox(),hud);
   assert(await page.locator('#matchScoreHud strong').evaluateAll(nodes=>nodes.every(n=>n.scrollWidth<=n.clientWidth)));
   const colors=[];
   for(const [name,time,status,expected] of [
    ['preparation',20,'upcoming','rgb(54, 224, 124)'],
    ['warning',45,'upcoming','rgb(150, 195, 80)'],
    ['spawning',70,'spawning','rgb(245, 166, 35)'],
    ['between-waves',100,'released','rgb(54, 224, 124)']]){
    const sample=await page.evaluate(({time,status})=>{
     const state=structuredClone(timelineFixture);state.server_time+=time;
     state.wave_timeline={...state.wave_timeline,time_s:time,end_s:210,waves:[{wave:1,start_s:60,end_s:90,duration_s:30,state:status},{wave:2,start_s:180,end_s:210,duration_s:30,state:'upcoming'}]};
     (typeof waveTimelines==='undefined'?[waveTimeline]:waveTimelines).forEach(timeline=>timeline.update(state));
     const fill=document.querySelector('.ltzWaveProgress'),head=document.querySelector('[data-playhead]');
     return {color:getComputedStyle(fill).fill,width:+fill.getAttribute('width'),head:head.getAttribute('transform'),opacity:getComputedStyle(fill).fillOpacity};
    },{time,status});
    assert.equal(sample.color,expected);assert.equal(sample.opacity,'1');assert(Math.abs(sample.width-960*time/210)<.001);
    assert.equal(sample.head,`translate(${20+sample.width} 0)`);
    if(surface==='screen'&&width===1366)await page.locator('#waveTimeline').screenshot({path:`${output}/${name}.png`});
    colors.push({name,...sample});
   }
   await page.evaluate(()=>{timelineFixture.server_time+=200;applyState(timelineFixture);});
   await page.evaluate(()=>{timelineFixture.paused=false;timelineFixture.server_time+=1;applyState(timelineFixture);});
   await page.waitForTimeout(150);assert.notEqual(await timeline.locator('[data-playhead]').getAttribute('transform'),before);
   await page.evaluate(()=>(typeof waveTimelines==='undefined'?[waveTimeline]:waveTimelines).forEach(timeline=>timeline.setConnected(false)));
   const disconnected=await timeline.locator('[data-playhead]').getAttribute('transform');await page.waitForTimeout(150);
   assert.equal(await timeline.locator('[data-playhead]').getAttribute('transform'),disconnected);
   assert.match(await timeline.locator('.ltzWaveClock').textContent(),/FEED PAUSED/);
   if(surface==='screen')assert.match(await page.locator('#purpleWaveTimeline .ltzWaveClock').textContent(),/FEED PAUSED/);
   await page.evaluate(()=>{timelineFixture.journey.phase='calibration';applyState(timelineFixture);});
   assert(await page.locator('#waveTimeline').isHidden());assert.deepEqual(errors,[]);
   assert(await page.locator('#matchScoreHud').isHidden());
   if(surface==='screen'){assert(await page.locator('#purpleScoreHud').isHidden());assert(await page.locator('#purpleWaveTimeline').isHidden());}
   checks.push({surface,width,...result,box,hud,barLayout,colors,errors});await page.close();
  }
  fs.writeFileSync(output+'/results.json',JSON.stringify(checks,null,2));console.log(JSON.stringify(checks));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
