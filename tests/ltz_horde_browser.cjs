/* Four concurrent real views; replay a measured 1,000-enemy frame, no game writes. */
const fs=require('node:fs'),assert=require('node:assert/strict');const {chromium}=require('playwright');
const fixture=JSON.parse(fs.readFileSync(process.argv[2], 'utf8')),origin=process.env.LTZ_SCORE_ORIGIN||'http://127.0.0.1:8132',output=process.argv[3]||'/tmp/ltz-horde-browser.json';
(async()=>{const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',args:['--disable-background-timer-throttling','--disable-renderer-backgrounding','--disable-backgrounding-occluded-windows']});const pages=[],errors=[];
try{
 for(const [name,path,width,height] of [['y-game','/s/gamemaster/p/laser-tag-y/game',1696,1080],['y-screen','/s/gamemaster/p/laser-tag-y/screen',1696,960],['phone','/s/green/p/mobile-ltz/',844,390],['tablet','/s/purple/p/mobile-ltz/',1180,820]]){
  const page=await browser.newPage({viewport:{width,height}});page.on('pageerror',e=>errors.push(name+': '+e.message));
  const base=await(await page.request.get(origin+'/s/gamemaster/p/mobile-ltz-api/api/state')).json();
  const scene={...base,...fixture,run_id:'horde-replay',journey:{phase:'playing',revision:1},progress:{status:'ready',participants:[]},result_save:{status:'playing'},next_loadouts:null,server_time:Date.now()/1000};delete scene.mobile_progress.latest_result;
  await page.route('**/api/state',r=>r.fulfill({json:scene}));await page.route('**/api/command',r=>r.fulfill({status:409,json:{error:'Read-only renderer replay'}}));
  await page.addInitScript(({scene})=>{
   const m=window.__horde={frames:[],assets:null,passes:[]};const clear=CanvasRenderingContext2D.prototype.clearRect;
   CanvasRenderingContext2D.prototype.clearRect=function(...a){if(this.canvas.id==='gameCanvas')m.frames.push(performance.now());return clear.apply(this,a)};
   let api;Object.defineProperty(window,'TowerDefenceView',{get:()=>api,set(v){api=v;const create=v.create;v.create=o=>create({...o,onAssetStatus:s=>{m.assets=s;o.onAssetStatus?.(s)},onPerformance:s=>{m.passes.push(s);if(m.passes.length>10)m.passes.shift()}})}});
   window.EventSource=class{constructor(){this.listeners={};let tick=0;this.timer=setInterval(()=>{const s=structuredClone(scene);tick++;s.sim_time+=tick*.25;s.runtime_time+=tick*.25;s.server_time=Date.now()/1000;s.kills+=tick;s.match_score.sequence+=tick;s.match_score.kill_credits+=tick;for(const e of s.enemies){if(!['aim','recover'].includes(e.combat?.state)){e.x+=Math.sin(tick*.06+e.id)*6;e.y+=Math.cos(tick*.04+e.id)*3}}for(const a of s.enemy_arrows||[]){a.launch_at+=tick*.25;a.impact_at+=tick*.25}for(const t of [...s.towers,...s.companions])t.last_fire_at=s.sim_time;if(tick===1)this.onopen?.();this.onmessage?.({data:JSON.stringify(s)})},250)}addEventListener(k,f){this.listeners[k]=f}close(){clearInterval(this.timer)}};
  },{scene});await page.goto(origin+path);await page.waitForFunction(()=>window.__horde.assets?.requested>0&&window.__horde.assets?.pending===0);pages.push({name,page});
 }
 for(const {page}of pages)await page.evaluate(()=>window.__horde.frames=[]);
 await new Promise(r=>setTimeout(r,15000));const results=[];
 for(const {name,page}of pages){const result=await page.evaluate(()=>{let f=window.__horde.frames;let d=f.slice(1).map((t,i)=>t-f[i]).sort((a,b)=>a-b);return {frames:f.length,average_fps:1000*(f.length-1)/(f.at(-1)-f[0]),frame_p95_ms:d[Math.floor(d.length*.95)],assets:window.__horde.assets,passes:window.__horde.passes,overflow:document.documentElement.scrollWidth>innerWidth}});results.push({name,...result});assert.equal(result.assets.failed,0);await page.screenshot({path:output.replace('.json','-'+name+'.png')});}
 assert.deepEqual(errors,[]);fs.writeFileSync(output,JSON.stringify({enemies:fixture.enemies.length,primaries:fixture.towers.length,companions:fixture.companions.length,seconds:15,results,errors},null,2));console.log(JSON.stringify(results));
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
