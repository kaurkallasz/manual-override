/* Real clients, repeated detector gaps, isolated fixture only. No arm motion. */
const assert=require('node:assert/strict'),fs=require('node:fs');
const {chromium}=require('playwright');
const origin=process.env.MARKER_FIXTURE_URL||'http://127.0.0.1:56053';
const output=process.env.MARKER_OUTPUT||'/tmp/marker-flicker-views';
if(!/^http:\/\/127\.0\.0\.1:(?!8000(?:\/|$))\d+$/.test(origin))throw Error('Isolated fixture required');
(async()=>{
 fs.mkdirSync(output,{recursive:true});
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const results=[];
 try{
  const request=await browser.newPage();
  await request.request.post(origin+'/__test/camera',{data:{enabled:true}});
  const photo=await request.request.get(origin+'/s/gamemaster/p/mobile-ltz-api/api/assets/mobile-camera.jpg');
  assert.equal(photo.status(),200);const jpeg=(await photo.body()).toString('base64');await request.close();
  for(const side of ['green','purple','gamemaster']){
   const gm=side==='gamemaster',page=await browser.newPage({viewport:gm?{width:1500,height:1100}:{width:844,height:390}});
   const errors=[],commands=[];page.on('pageerror',e=>errors.push(e.message));
   page.on('request',r=>{if(r.method()==='POST'&&!r.url().includes('/api/diagnostics'))commands.push(r.url());});
   await page.route('**/p/mobile-ltz/api/physical-controller',r=>r.fulfill({status:503,json:{error:'Fixture arm disconnected'}}));
   await page.addInitScript(()=>{
    localStorage.setItem('mobile-ltz:stopped','yes');
    // Keep deterministic snapshots independent of the fixture's periodic feed.
    window.EventSource=class{addEventListener(){}close(){}};
   });
   await page.goto(origin+`/s/${side}/p/${gm?'laser-tag-y/game':'mobile-ltz/'}`);
   await page.waitForFunction(gm=>gm?!!ui.state:!!state,gm);
   const result=await page.evaluate(async({gm,jpeg})=>{
    const initial=structuredClone(gm?ui.state:state),piece=gm?100:team==='green'?100:102;
    const codes=[38,40,41,44,piece],counts=[];let learnedAt=Date.now()/1000;
    const tags=()=>codes.map((id,i)=>({id,last_seen:Date.now()/1000,camera:[.2+i*.14,.35+i%2*.15],
     corners:[[.19+i*.14,.34+i%2*.15],[.21+i*.14,.34+i%2*.15],[.21+i*.14,.36+i%2*.15],[.19+i*.14,.36+i%2*.15]]}));
    function update(i,empty=false){
     const now=Date.now()/1000,visible=empty||i%4===2?[]:tags();
     if(i===0)learnedAt=now;
     const fixed=codes.filter(id=>id<100).map((id,i)=>({id,nx:.2+i*.14,ny:.35+i%2*.15,last_seen:learnedAt,fixed:true,visible:false}));
     if(i>=10)fixed.push({id:55,nx:.8,ny:.7,last_seen:now,fixed:true,visible:false});
     const tracking={contract:'photon.board.camera-markers',version:1,status:'ready',source:'camera',
      camera_identity:'fixture',camera_revision:'fixed',coordinate_space:'corrected-camera-normalized',
      frame_at:now,server_time:now,width:1280,height:720,max_age_s:1.5,tags:visible,size_filter:{rejected:[{id:38,reason:'size_outlier'},{id:40,reason:'size_outlier'},{id:piece,reason:'size_outlier'}]}};
     const packet={...initial,virtual_play:false,server_time:now,virtual_test_control:4,mobile_arm:null,
      inputs:{...initial.inputs,board:{status:'ready',upstream:{source:'camera'}}},
      mobile_camera:{...initial.mobile_camera,tracking},movable_piece_codes:{green:[100,101],purple:[102,103]},
      mobile_cue_targets:{contract:'photon.board.cue-targets',version:2,status:empty?'unavailable':'ready',source:'camera',epoch:'fixed',scope:'game',width:1280,height:720,
       sampled_at:now,fixed_tags:fixed,blocked_fixed_ids:[],pending_fixed_ids:[40],quarantined_tags:[{id:40,reason:'marker_geometry'}],
       coordinate_space:'corrected-camera-normalized',server_time:now,frame_at:now,
       tags:visible.map(t=>({id:t.id,nx:t.camera[0],ny:t.camera[1],last_seen:t.last_seen,fixed:t.id<100,visible:true}))}};
     applyState(packet);
     if(gm){
      operatorCamera.frame({contract:'laser-tag-y.camera',version:1,status:'ready',frame_at:now,width:1280,height:720,image:'data:image/jpeg;base64,'+jpeg});
      arucoMonitor.setEnabled(true);
      arucoMonitor.update({contract:'photon.board.tracking',version:1,status:'ready',tags:[],camera_markers:tracking,fixed_board:packet.mobile_cue_targets});
     }else drawMarkerLabels();
    }
    if(gm)arucoMonitor.resetCache();else liveFeed.stop();
    await new Promise(r=>setTimeout(r,20));
    for(let i=0;i<20;i++){
     update(i);await new Promise(r=>setTimeout(r,180));
     counts.push(gm?document.querySelectorAll('#arucoOverlay text').length:document.querySelectorAll('#markerLabels .markerNumber').length);
    }
    update(20,true);await new Promise(r=>setTimeout(r,1150));if(gm)arucoMonitor.check();else drawMarkerLabels();
    const afterOcclusion=gm?document.querySelectorAll('#arucoOverlay text').length:document.querySelectorAll('#markerLabels .markerNumber').length;
    return {counts,expected:codes.length,afterOcclusion,motionReady:gm?false:available()};
   },{gm,jpeg});
   assert(result.counts.every((n,i)=>n===result.expected+(i>=10?1:0)),side+': labels flashed '+JSON.stringify(result.counts));
   assert.equal(result.afterOcclusion,5,'Fixed core/socket labels survive camera outage; moving Atom expires');assert.equal(result.motionReady,false);assert.deepEqual(errors,[]);assert.deepEqual(commands,[]);
   await page.screenshot({path:`${output}/${side}.png`});
   results.push({side,...result,errors,commands});await page.close();
  }
  fs.writeFileSync(output+'/results.json',JSON.stringify(results,null,2));console.log(JSON.stringify(results));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
