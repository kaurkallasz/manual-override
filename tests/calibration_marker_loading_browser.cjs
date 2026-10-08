/* Real projection + OpenCV markers, isolated fake-arm fixture only. */
const assert=require('node:assert/strict'),{spawnSync}=require('node:child_process');
const {chromium}=require('playwright');
const root=process.env.MOBILE_XYZ_TEST_URL||'http://127.0.0.1:8134';
function detected(path){
 const result=spawnSync('.venv/bin/python',['-c',
  'import cv2,json,sys; image=cv2.imread(sys.argv[1]); detector=cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)); _,ids,_=detector.detectMarkers(image); print(json.dumps(sorted(ids.flatten().tolist()) if ids is not None else []))',path],{encoding:'utf8'});
 assert.equal(result.status,0,result.stderr);return JSON.parse(result.stdout);
}
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 try{
  for(const side of ['green','purple']){
   const ctx=await browser.newContext({viewport:{width:1280,height:720}}),hold=await ctx.newPage();
   const response=await ctx.request.post(root+'/s/gamemaster/p/photon-game/api/command',{data:{action:'calibration_test',side}});
   assert(response.ok(),await response.text());
   await hold.route('**/__test/hold',route=>route.fulfill({contentType:'text/html',body:'<!doctype html><title>Isolated event streams</title>'}));
   await hold.goto(root+'/__test/hold');
   await hold.evaluate(()=>{
    window.opened=0;window.streams=Array.from({length:5},(_,i)=>{
     const s=new EventSource('/s/gamemaster/p/playfield-areas/api/events?hold='+i);
     s.onopen=()=>window.opened++;return s;
    });
   });
   await hold.waitForFunction(()=>window.opened===5);
   const page=await ctx.newPage(),errors=[],completed=new Set();let rejected=false;
   page.on('pageerror',e=>errors.push(e.message));
   page.on('requestfinished',r=>{if(/\/api\/marker\/\d+$/.test(r.url()))completed.add(r.url());});
   // Also prove that a failed texture does not remain a permanently black code.
   if(side==='purple')await page.route('**/api/marker/30',route=>{
    if(!rejected){rejected=true;return route.fulfill({status:503,contentType:'text/plain',body:'Temporary marker failure'});}
    return route.continue();
   });
   await page.goto(root+'/s/gamemaster/p/playfield-areas/screen?presentation=1',{waitUntil:'domcontentloaded'});
   if(side==='purple')await page.waitForFunction(()=>document.getElementById('markerStatus').textContent.includes('unavailable'));
   // No other stream is closed to make room: the screen must release its own.
   await page.waitForFunction(()=>document.getElementById('markerStatus')?.hidden===true
    &&performance.getEntriesByType('resource').filter(r=>/\/api\/marker\/\d+$/.test(r.name)&&r.responseStatus===200).length>=6,null,{timeout:15000});
   assert.equal(completed.size,6,'All six image requests complete alongside five event streams');
   await page.screenshot({path:`/tmp/calibration-markers-${side}-fixed.png`});
   assert.deepEqual(detected(`/tmp/calibration-markers-${side}-fixed.png`),[30,31,32,33,34,35],'Projected codes remain machine-readable in both layouts');
   assert.equal(await hold.evaluate(()=>window.streams.filter(s=>s.readyState===EventSource.OPEN).length),5);
   assert.deepEqual(errors,[]);
   await hold.evaluate(()=>window.streams.forEach(s=>s.close()));
   // The live feed must resume after image loading/retry and receive a new layout.
   const other=side==='green'?'purple':'green';
   assert((await ctx.request.post(root+'/s/gamemaster/p/photon-game/api/command',{data:{action:'calibration_test',side:other}})).ok());
   const layout=await ctx.request.get(root+'/s/gamemaster/p/playfield-areas/api/state').then(r=>r.json());
   // Number/code coordinates rotate 180 degrees between teams. Check rendered
   // pixels via marker detection instead of relying on implementation variables.
   const expectedLeft=layout.areas.filter(a=>a.x<0).map(a=>a.marker).sort();
   const before=`/tmp/calibration-markers-${side}-switched.png`;
   await page.waitForTimeout(500);await page.screenshot({path:before});
   const left=spawnSync('.venv/bin/python',['-c',
    'import cv2,json,sys; image=cv2.imread(sys.argv[1]); detector=cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)); corners,ids,_=detector.detectMarkers(image); print(json.dumps(sorted(int(i) for c,i in zip(corners,ids.flatten()) if c.reshape(-1,2)[:,0].mean()<image.shape[1]/2)))',before],{encoding:'utf8'});
   assert.equal(left.status,0,left.stderr);assert.deepEqual(JSON.parse(left.stdout),expectedLeft,'Live layout updates resume after loading');
   await ctx.close();console.log(`PASS ${side}: six decodable calibration codes with five other SSE streams, retry and live layout updates`);
  }
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
