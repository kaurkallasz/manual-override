// Real Green/Purple pages and temporary profiles, with randomUUID unavailable.
const assert=require('node:assert/strict'),{chromium}=require('playwright');
const origin='http://127.0.0.1:8117';
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const errors=[],verified=[];
 try{
  for(const side of ['green','purple']){
   for(const slug of ['ltz-score','mobile-ltz']){
    const page=await browser.newPage({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
    page.on('pageerror',error=>{errors.push(`${side}/${slug}: ${error.message}`);console.error(errors.at(-1));});
    await page.addInitScript(noCrypto=>{
     Object.defineProperty(crypto,'randomUUID',{value:undefined});
     if(noCrypto)Object.defineProperty(crypto,'getRandomValues',{value:undefined});
     localStorage.setItem('mobile-ltz:stopped','yes');localStorage.setItem('mobile-ltz:purple:stopped','yes');
    },side==='purple'&&slug==='ltz-score');
    await page.goto(`${origin}/s/${side}/p/${slug}/`);
    assert.equal(await page.evaluate(()=>typeof crypto.randomUUID),'undefined');
    if(slug==='mobile-ltz'){
     await page.waitForFunction(()=>view?.levelReady);
     await page.locator('#levelsOpen').click();await page.locator('#openPlayers').click();
    }
    const selector=slug==='ltz-score'?'#playerSelect':'#journeyPlayer';
    await page.waitForSelector(selector+` option[value="ltz-test-${side}"]`,{state:'attached'});
    assert.match(await page.locator(selector+` option[value="ltz-test-${side}"]`).textContent(),/Practice only/);
    const name=`${side} ${slug} ${Date.now().toString(36)}`;
    await page.locator(slug==='ltz-score'?'#playerName':'#journeyNewName').fill(name);
    await page.locator(slug==='ltz-score'?'#createPlayer':'#journeyCreate').click();
    await page.waitForFunction(({selector,name})=>document.querySelector(selector)?.selectedOptions[0]?.textContent.includes(name),{selector,name});
    const state=await page.request.get(`${origin}/s/gamemaster/p/photon-progress/api/state?side=${side}`).then(response=>response.json());
    assert.equal(state.player.name,name);assert.equal(state.player.is_test,false);
    assert.equal(state.players.filter(p=>p.name===name).length,1);
    await page.locator(selector).selectOption('ltz-test-'+side);
    if(slug==='ltz-score')await page.locator('#loadPlayer').click();
    await page.waitForFunction(({selector,side})=>document.querySelector(selector)?.value==='ltz-test-'+side,{selector,side});
    const status=slug==='ltz-score'?'#statsPlayer':'#journeyContent';
    await page.waitForFunction(selector=>document.querySelector(selector)?.textContent.includes('Practice only'),status);
    if(slug==='mobile-ltz')await page.locator('#journeyToggle').click();
    const dataset=slug==='ltz-score'?'#dataset':'[data-filter="dataset"]';
    await page.waitForFunction(selector=>document.querySelector(selector)?.value==='practice',dataset);
    assert.equal(await page.locator(dataset).inputValue(),'practice',`${side}/${slug}`);
    const selected=await page.request.get(`${origin}/s/gamemaster/p/photon-progress/api/state?side=${side}`).then(response=>response.json());
    assert.equal(selected.player.id,'ltz-test-'+side);assert.equal(selected.player.is_test,true);
    await page.screenshot({path:`/tmp/ltz-${side}-${slug}-test-player.png`});
    verified.push(`${side}/${slug}: create and select without randomUUID, selectable test profile`);
    await page.close();
   }
  }
  assert.deepEqual(errors,[]);console.log(JSON.stringify({verified,errors}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
