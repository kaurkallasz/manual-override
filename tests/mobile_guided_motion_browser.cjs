// Real renderer + engine, isolated fixture only; intentionally drops received updates.
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  try{
    const page=await browser.newPage({viewport:{width:844,height:390},isMobile:true,hasTouch:true});
    const errors=[];page.on('pageerror',error=>errors.push(error.message));
    await page.addInitScript(()=>localStorage.setItem('mobile-ltz:stopped','yes'));
    await page.goto('http://127.0.0.1:8117/s/green/p/mobile-ltz/');
    await page.request.post('http://127.0.0.1:8117/__test/command',{data:{action:'start'}});
    await page.waitForFunction(()=>state?.enemies?.some(e=>e.motion?.mode==='road'&&e.motion.speed>0));
    const guide=await page.evaluate(()=>({contract:state.enemy_motion,revision:state.row_topology_revision,mode:state.enemies[0].motion.mode}));
    assert.equal(guide.contract.version,1);assert.equal(guide.contract.horizon_s,1.2);
    const gaps=[];
    for(const duration of [900,1200,900]){
      const result=await page.evaluate(async duration=>{
        const receive=gameState.receive.bind(gameState);let latest=null;let drops=0;
        gameState.receive=(...args)=>{latest=args;drops++;return gameState.value;};
        // The actual Canvas loop keeps rendering the last accepted snapshot.
        const reports=[];const began=performance.now();
        while(performance.now()-began<duration){await new Promise(r=>setTimeout(r,50));reports.push({...window.mobilePerformance});}
        gameState.receive=receive;if(latest)receive(...latest);
        return {duration,drops,maxPrediction:Math.max(...reports.map(r=>r.predictionPercent||0)),maxAge:Math.max(...reports.map(r=>r.updateAgeMs||0)),fps:Number(document.getElementById('fps').textContent)};
      },duration);
      assert.ok(result.drops>0);assert.ok(result.fps>0);gaps.push(result);
      await page.waitForTimeout(1100);
    }
    assert.ok(gaps.some(g=>g.maxPrediction>0),'actual Canvas loop uses prediction through a receive gap');
    await page.request.post('http://127.0.0.1:8117/__test/command',{data:{action:'reset'}});
    await page.waitForFunction(()=>state.phase==='setup'&&state.enemies.length===0);
    assert.deepEqual(errors,[]);
    console.log(JSON.stringify({guide,gaps,resetClearedEnemies:true,errors}));
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
