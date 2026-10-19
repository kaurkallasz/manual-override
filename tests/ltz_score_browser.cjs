const assert=require('node:assert/strict'),fs=require('node:fs');
const {chromium}=require('playwright');
const origin=process.env.LTZ_SCORE_ORIGIN||'http://127.0.0.1:8131',output='/tmp/ltz-score-views';
(async()=>{
 fs.mkdirSync(output,{recursive:true});
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const results=[];
 try{
  for(const [name,path,width,height] of [
   ['phone-small','/s/green/p/mobile-ltz/',667,320],['phone','/s/green/p/mobile-ltz/',844,390],
   ['tablet','/s/purple/p/mobile-ltz/',1024,768],['tablet-wide','/s/purple/p/mobile-ltz/',1180,820],
   ['score-green','/s/green/p/ltz-score/',1280,900],['score-purple','/s/purple/p/ltz-score/',1280,900],
   ['y-game','/s/gamemaster/p/laser-tag-y/game',1696,1080],['y-screen','/s/gamemaster/p/laser-tag-y/screen',1696,960]]){
   const page=await browser.newPage({viewport:{width,height}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
   await page.addInitScript(()=>localStorage.setItem('mobile-ltz:stopped','yes'));
   await page.request.post(origin+'/__test/result');
   await page.goto(origin+path);await page.waitForTimeout(1600);
   const mobile=path.includes('mobile-ltz'),shop=!name.startsWith('y-');
   if(shop)await page.locator('.ltzCard').first().waitFor();
   const result=await page.evaluate(()=>({cards:document.querySelectorAll('.ltzCard').length,
    receipt:document.querySelector('.ltzReceipt')?.innerText,
    overflow:document.documentElement.scrollWidth>innerWidth,
    missingImages:[...document.images].filter(i=>i.src.includes('shop/')&&i.complete&&!i.naturalWidth).map(i=>i.src),
    bodyText:document.body.innerText.slice(-400)}));
   assert(!result.overflow, name+' horizontal overflow');if(shop){assert.equal(result.cards,15);assert(result.receipt?.toLowerCase().includes('result saved'));assert(result.receipt.includes('Center stack victory'));assert.deepEqual(result.missingImages,[]);}
   assert.deepEqual(errors,[],name+' errors');
   if(mobile){const buy=page.locator('[data-upgrade="damage-machine-gun"][data-level="2"]');if(await buy.isEnabled()){await buy.click();await page.waitForTimeout(500);assert.match(await page.locator('#journeyMessage').innerText(),/Paid|Saved/);}}
   await page.screenshot({path:output+'/'+name+'.png'});results.push({name,...result,errors});await page.close();
  }
  fs.writeFileSync(output+'/results.json',JSON.stringify(results,null,2));console.log(JSON.stringify(results));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
