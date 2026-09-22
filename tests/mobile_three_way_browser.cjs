// Legacy filename; isolated fixture only. Two exclusive, independently clearable pump toggles.
const assert=require('node:assert/strict');const {chromium}=require('playwright');
(async()=>{const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
try{
 const page=await browser.newPage({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
 await page.addInitScript(()=>localStorage.setItem('mobile-ltz:stopped','yes'));
 const errors=[],pumps=[];page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.url().endsWith('/api/command')&&r.postDataJSON()?.action==='pump')pumps.push(r.postDataJSON().mode);});
 await page.goto('http://127.0.0.1:8117/s/green/p/mobile-ltz/');
 const suck=page.getByRole('button',{name:'Suck',exact:true}),blow=page.getByRole('button',{name:'Blow',exact:true});
 assert.equal(await page.locator('#pumpMode').count(),0);assert.equal(await page.getByRole('button',{name:'Off',exact:true}).count(),0);
 assert.equal(await suck.isDisabled(),true);assert.equal(await blow.isDisabled(),true);
 await page.locator('#connect').click();await page.waitForFunction(()=>document.getElementById('connection').textContent==='Connected');
 for(const [button,mode] of [[suck,'suction'],[blow,'blow'],[blow,'off'],[suck,'suction'],[suck,'off']]){
  await button.click();await page.waitForFunction(()=>!document.getElementById('pumpButtons').hasAttribute('aria-busy'));
  assert.equal(await suck.getAttribute('aria-pressed'),String(mode==='suction'));
  assert.equal(await blow.getAttribute('aria-pressed'),String(mode==='blow'));
  assert.equal(pumps.at(-1),mode);
 }
 assert.deepEqual(pumps,['suction','blow','off','suction','off']);
 for(const [width,height] of [[390,844],[320,568],[844,390]]){
  await page.setViewportSize({width,height});
  for(const button of [suck,blow]){const b=await button.boundingBox();assert.ok(b.x>=0&&b.y>=0&&b.x+b.width<=width+.1&&b.y+b.height<=height+.1);assert.ok(b.width>=26&&b.height>=20);const dial=await page.locator('.baseDial').boundingBox();assert.ok(b.x>=dial.x&&b.x+b.width<=dial.x+dial.width&&b.y>=dial.y&&b.y+b.height<=dial.y+dial.height);}
 }
 await page.locator('#stop').click();assert.deepEqual(errors,[]);
 console.log(JSON.stringify({exclusive:true,toggleOff:true,pumps,errors}));
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
