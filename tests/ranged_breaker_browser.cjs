/* Real shared renderer on both Y views and landscape Mobile; isolated fixture only.
   Start tests/ranged_breaker_fixture.py first. NODE_PATH=<bundled packages> node ... */
const assert=require('node:assert/strict'),fs=require('node:fs');
const {chromium}=require('playwright');
const origin=process.env.ARCHER_FIXTURE_ORIGIN||'http://127.0.0.1:8129';
const output=process.env.ARCHER_OUTPUT||'/tmp/archer-views';
(async()=>{
 fs.mkdirSync(output,{recursive:true});
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const results=[];
 try{
  for(const [name,path,width,height,mobile] of [
   ['y-game','/s/gamemaster/p/laser-tag-y/game',1696,1080,false],
   ['y-screen','/s/gamemaster/p/laser-tag-y/screen',1696,960,false],
   ['phone','/s/green/p/mobile-ltz/',844,390,true],
   ['tablet','/s/purple/p/mobile-ltz/',1180,820,true]]){
   const page=await browser.newPage({viewport:{width,height},isMobile:mobile,hasTouch:mobile});
   const errors=[],badAssets=[];
   page.on('pageerror',e=>errors.push(e.message));
   page.on('response',r=>{if(r.url().includes('archer-atlas')&&r.status()!==200)badAssets.push(r.status());});
   await page.addInitScript(()=>{
    localStorage.setItem('mobile-ltz:stopped','yes');
    window.__archer={frames:[],assets:null,combat:null,arrows:0,archers:0,drawn:0};
    // Metadata alone passed even when an old renderer drew hammer orcs.
    // Follow atlas frames through the orientation cache to the visible canvas.
    const archerImages=new WeakSet();let art;
    Object.defineProperty(window,'BreakerRenderer',{get:()=>art,set(v){art=v;const frames=v.frames;v.frames=image=>{
     const result=frames(image);result.forEach(frame=>archerImages.add(frame));return result;
    };}});
    const draw=CanvasRenderingContext2D.prototype.drawImage;
    CanvasRenderingContext2D.prototype.drawImage=function(source,...args){
     if(archerImages.has(source)){if(this.canvas.id==='gameCanvas')window.__archer.drawn++;else archerImages.add(this.canvas);}
     return draw.call(this,source,...args);
    };
    let api;
    Object.defineProperty(window,'TowerDefenceView',{get:()=>api,set(v){api=v;const create=v.create;v.create=options=>{
     const view=create({...options,onAssetStatus:s=>{window.__archer.assets=s;options.onAssetStatus?.(s);}});
     const apply=view.applyState;view.applyState=s=>{window.__archer.combat=s.enemy_combat;window.__archer.arrows=Math.max(window.__archer.arrows,s.enemy_arrows?.length||0);window.__archer.archers=(s.enemies||[]).filter(e=>e.combat?.variant==='archer').length;return apply(s);};return view;
    };}});
    const clear=CanvasRenderingContext2D.prototype.clearRect;
    CanvasRenderingContext2D.prototype.clearRect=function(...args){if(this.canvas.id==='gameCanvas')window.__archer.frames.push(performance.now());return clear.apply(this,args);};
   });
   await page.goto(origin+path);
   await page.waitForFunction(()=>window.__archer.assets?.pending===0&&window.__archer.assets?.requested>0&&window.__archer.combat?.breaker_mode==='ranged',{},{timeout:30000});
   await page.waitForTimeout(5000);
   const result=await page.evaluate(()=>{
    const s=window.__archer,f=s.frames.slice(60),d=f.slice(1).map((x,i)=>x-f[i]).sort((a,b)=>a-b);
    return {assets:s.assets,combat:s.combat,archers:s.archers,drawn:s.drawn,peakArrows:s.arrows,frameP95:d[Math.floor(d.length*.95)],
     imageLoaded:performance.getEntriesByType('resource').some(r=>r.name.includes('archer-atlas')),
     overflow:document.documentElement.scrollWidth>innerWidth};
   });
   assert.equal(result.assets.failed,0);assert(result.imageLoaded);assert(result.archers>0);
   assert(result.drawn>0,'archer atlas sprites must actually reach the visible game canvas');
   assert(result.peakArrows>0);assert(!result.overflow);
   assert.deepEqual(errors,[]);assert.deepEqual(badAssets,[]);
   await page.screenshot({path:output+'/'+name+'.png'});
   results.push({name,...result,errors});await page.close();
  }
  const page=await browser.newPage({viewport:{width:1152,height:960}});
  await page.goto(origin+'/s/gamemaster/p/laser-tag-y/screen');
  await page.waitForFunction(()=>window.BreakerRenderer);
  await page.evaluate(async()=>{
   const s=await(await fetch('/s/gamemaster/p/photon-game/api/state')).json();
   const image=new Image();image.src='/s/gamemaster'+s.presentation.base+'/'+s.presentation.assets['enemy/breaker/archer-atlas'];await image.decode();
   const frames=BreakerRenderer.frames(image);document.body.replaceChildren();document.body.style='margin:0;background:#263c32';
   const c=document.createElement('canvas');c.width=1152;c.height=960;document.body.append(c);const x=c.getContext('2d');
   x.fillStyle='#263c32';x.fillRect(0,0,c.width,c.height);x.fillStyle='white';x.font='17px system-ui';
   ['Walk 1','Walk 2','Walk 3','Walk 4','Aim','Draw','Release','Recover'].forEach((t,i)=>x.fillText(t,i*144+20,25));
   for(let r=0;r<8;r++)for(let i=0;i<8;i++){x.save();x.translate(i*144+72,r*115+88);x.rotate(r*Math.PI/4);x.drawImage(frames[i],-49,-49,98,98);x.restore();}
  });
  await page.screenshot({path:output+'/poses-directions.png'});
  fs.writeFileSync(output+'/results.json',JSON.stringify(results,null,2));console.log(JSON.stringify(results));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
