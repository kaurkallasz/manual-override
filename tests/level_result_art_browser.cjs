/* Exact L3 result-art/graph regression; real shared UI and PNGs, no hardware.
 * Run: NODE_PATH=<Playwright node_modules> node tests/level_result_art_browser.cjs */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require('playwright');
const output='output/level-results-2026-10-18';
const history=[0,968,9,0,270,0,182].map((score,i)=>({level:[1,1,2,2,2,2,3][i],score,assisted:i===3}));
const players=[{player_id:'green-player',name:'Ari',side:'green'},{player_id:'purple-player',name:'Mira',side:'purple'}];
const result={run_id:'l3-art-regression',player_id:players[0].player_id,side:'green',outcome:'won',unlocked_control:4,total_earned:182,stack_bonus:0,balance:182,active_seconds:154,
 statistics:{level:3,total_kills:182,score:182,players,kill_attribution:{green:90,purple:80,shared:12},history,history_total:7,turrets_unlocked:{},atoms_unlocked:[{player_id:players[0].player_id,track:'damage-flamethrower',level:1},{player_id:players[1].player_id,track:'damage-tesla-coil',level:1}]}};
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const errors=[];
 try{
  fs.mkdirSync(output,{recursive:true});
  for(const [name,width,height,reduced,observer] of [['landscape',844,390,false,'html-only'],['portrait',390,844,false,'html-only'],['desktop',1440,1000,false,'html-only'],['reduced',390,844,true,'html-only'],['no-observer-callback',844,390,false,'silent']]){
   const page=await browser.newPage({viewport:{width,height},reducedMotion:reduced?'reduce':'no-preference'});
   page.on('pageerror',e=>errors.push(e.message));
   await page.route('https://result.test/assets/**',route=>{
    const relative=new URL(route.request().url()).pathname.slice('/assets/'.length);
    const file=path.resolve('sandboxes/gamemaster/prototypes/photon-level/assets',relative);
    assert(file.startsWith(path.resolve('sandboxes/gamemaster/prototypes/photon-level/assets')+path.sep));
    return route.fulfill({path:file});
   });
   await page.setContent('<style>body{margin:0;background:#061019}#scroll{height:100vh;overflow:auto;padding:12px;box-sizing:border-box}</style><main id="scroll"><div id="result"></div></main>');
   await page.addStyleTag({content:fs.readFileSync('shared/ltz_ui/shop.css','utf8')});
   // Reproduce browsers that never report SVG shape intersections. Only the
   // HTML chart may be observed. A completely silent observer must still leave
   // the saved chart readable, including zero scores and a single first game.
   await page.evaluate(mode=>{
    const RealObserver=window.IntersectionObserver;window.observedSvg=0;
    window.IntersectionObserver=class extends RealObserver{observe(node){if(node instanceof SVGElement){window.observedSvg++;return;}if(mode!=='silent')super.observe(node);}};
   },observer);
   await page.addScriptTag({content:fs.readFileSync('shared/ltz_ui/shop.js','utf8')});
   const render=async receipt=>page.evaluate(r=>{LTZShop.configure({asset:id=>'https://result.test/assets/'+id});document.querySelector('#result').innerHTML=LTZShop.receipt(r);LTZShop.mount(document.querySelector('#result'));},receipt);
   await render(result);
   await page.locator('.ltzHistoryPlot').scrollIntoViewIfNeeded();
   if(observer!=='silent'&&!reduced)await page.waitForFunction(()=>!document.querySelector('.ltzHistoryPlot').hasAttribute('data-waiting'));
   await page.waitForFunction(()=>[...document.querySelectorAll('.ltzHistoryDot,.ltzHistoryLine,.ltzHistoryArea')].every(n=>getComputedStyle(n).opacity==='1'&&getComputedStyle(n).visibility==='visible'&&n.getBoundingClientRect().width>0));
   assert.equal(await page.evaluate(()=>window.observedSvg),0,'Do not depend on SVG shape intersection');
   assert.equal(await page.locator('.ltzHistoryDot').count(),7);
   assert.equal(await page.locator('.ltzHistoryDot.assisted').count(),1);
   assert.equal(await page.locator('.ltzHistoryLine').getAttribute('points').then(p=>p.split(' ').length),7);
   await page.screenshot({path:output+'/l3-'+name+'-journey.png'});
   if(observer!=='silent'){
    await page.locator('.ltzUnlockSection').scrollIntoViewIfNeeded();
    await page.waitForFunction(()=>[...document.querySelectorAll('.ltzUnlock')].every(n=>!n.hasAttribute('data-waiting')&&getComputedStyle(n).opacity==='1'));
    await page.waitForFunction(()=>[...document.querySelectorAll('.ltzUnlock img')].every(n=>n.complete&&n.naturalWidth>0));
    assert.equal(await page.locator('.ltzUnlock img').count(),2);
    assert.match(await page.locator('.ltzUnlockSection').textContent(),/Flamethrower[\s\S]*Tesla Coil/);
    await page.screenshot({path:output+'/l3-'+name+'-unlocks.png'});
    // Replay and replacement during SSE keep real chart marks visible.
    await page.locator('.ltzReplay').click();await page.locator('.ltzHistoryPlot').scrollIntoViewIfNeeded();
    await page.waitForFunction(()=>[...document.querySelectorAll('.ltzHistoryDot')].every(n=>getComputedStyle(n).opacity==='1'));
    await render(result);await page.locator('.ltzHistoryPlot').scrollIntoViewIfNeeded();
    await page.waitForFunction(()=>[...document.querySelectorAll('.ltzHistoryDot')].every(n=>getComputedStyle(n).opacity==='1'));
   }
   await render({...result,run_id:'first-zero-'+name,statistics:{...result.statistics,history:[{score:0,level:3}],history_total:1}});
   await page.locator('.ltzHistoryPlot').scrollIntoViewIfNeeded();
   await page.waitForFunction(()=>getComputedStyle(document.querySelector('.ltzHistoryDot')).opacity==='1');
   assert.equal(await page.locator('.ltzHistoryDot').count(),1);assert.equal(await page.locator('.ltzHistoryDot').getAttribute('cy'),'132');
   await page.close();
  }
  assert.deepEqual(errors,[]);
  console.log('PASS: L3 T1 images; seven visible history marks, zero and first-game scores; HTML-only/silent observers; replay and replacement; landscape, portrait, desktop and reduced motion.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
