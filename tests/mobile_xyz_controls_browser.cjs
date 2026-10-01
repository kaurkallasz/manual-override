// Real shared mobile + LTX bridge, isolated Game, fake calibration/robot only.
// Run against tests/mobile_ltz_fixture.py on 8117. Never contacts hardware.
const assert=require('node:assert/strict'),{chromium}=require('playwright');
const origin='http://127.0.0.1:8117';
const points=[[.1,.2,240,-100],[.5,.15,320,-110],[.9,.2,400,-100],[.9,.8,400,100],[.5,.85,320,110],[.1,.8,240,100]];
const arm={points:Object.fromEntries(points.map(([u,v,x,y],i)=>['p'+(i+1),{camera:{u,v},pose:{x,y,z:60,r:9,set:true}}]))};
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const errors=[],players=[],verified=[];
 try{
  const gm=await browser.newPage();gm.on('pageerror',e=>errors.push('GM: '+e.message));
  await gm.request.post(origin+'/__test/command',{data:{action:'reset'}});
  await gm.request.post(origin+'/__test/command',{data:{action:'virtual_test_loadout',control:1,levels:null}});
  await gm.request.post(origin+'/__test/camera',{data:{enabled:true}});
  await gm.goto(origin+'/s/gamemaster/p/laser-tag-y/');await gm.waitForFunction(()=>ui.state?.status==='ready');
  for(const team of ['green','purple']){
   const page=await browser.newPage({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
   const robot={pose:[300,0,60,9],joints:[0,20,30,9],target:[0,20,30,9],control_mode:'joint'},commands=[];
   page.on('pageerror',e=>errors.push(team+': '+e.message));
   await page.route('**/auto-pickup-game/api/calibration2',route=>route.fulfill({json:{ok:true,calibration:{enabled:true,arms:{green:arm,purple:arm},shared_z:{transport_height:80},radius_min:220,radius_max:440}}}));
   await page.route('**/cartesian-xyz-test/api/**',async route=>{
    const action=new URL(route.request().url()).pathname.split('/').at(-1);
    if(action==='config')return route.continue();
    const data=route.request().postDataJSON();
    if(data){
     commands.push({action,data});
     if(action==='move'){robot.pose=['x','y','z','r'].map(k=>data[k]);robot.target=[...robot.pose];robot.control_mode='cartesian';}
    }
    return route.fulfill({json:{ok:true,connected:true,enabled:true,feedback_ok:true,last_feedback:Date.now()/1000,pump_mode:'off',...robot}});
   });
   await page.goto(origin+`/s/${team}/p/mobile-ltz/`);
   await page.waitForFunction(()=>physicalArm.arm()&&feedReady);
   await page.locator('#connect').click();await page.waitForFunction(()=>!!session&&available());
   players.push({team,page,robot,commands,token:await page.evaluate(()=>session)});
  }
  for(const [index,mode] of ['joint','xyz','targeting','cue','xyz','joint'].entries()){
   const tier={joint:1,xyz:2,targeting:3,cue:4}[mode];
   await gm.locator('#testOverride').check();await gm.locator('#testMobileControl').selectOption(String(tier));await gm.locator('#applyTestUnlocks').click();
   await gm.waitForFunction(t=>ui.state.virtual_test_control===t,tier);
   for(const player of players){
    const {team,page,robot,commands,token}=player;
    await page.waitForFunction(m=>controlMode===m&&available(),mode);
    assert.equal(await page.evaluate(()=>session),token,team+' connection survives GM '+mode);
    assert.equal(commands.filter(c=>c.action==='connect').length,1,'Mode changes do not reacquire the relay');
    if(mode==='joint')continue;
    for(const [axis,amount] of [['z',1],...(mode==='xyz'?[['x',10],['y',10]]:[])]){
     for(const direction of [1,-1]){
      const before=await page.evaluate(axis=>xyzTarget[axis],axis),beforeXY=robot.pose.slice(0,2),count=commands.filter(c=>c.action==='move').length;
      await page.locator('#xyz'+axis.toUpperCase()+(direction===1?'Increase':'Decrease')).click();
      await page.waitForFunction(()=>!pendingXYZ&&!xyzSending&&!inflight);
      assert(commands.filter(c=>c.action==='move').length>count,team+' '+mode+' '+axis+' sends through LTX');
      const orientation=axis==='z'?1:await page.evaluate(()=>viewport.direction);
      assert(Math.abs((await page.evaluate(axis=>xyzTarget[axis],axis))-before-direction*amount*orientation)<.001,team+' '+axis+' exact screen-direction increment');
      if(axis==='z')assert.deepEqual(robot.pose.slice(0,2),beforeXY,'Height preserves measured robot XY');
      assert.equal(await page.evaluate(()=>session),token);
     }
    }
    await page.locator('#xyzPrecision').click();
    for(const [axis,amount] of [['z',.1],...(mode==='xyz'?[['x',1],['y',1]]:[])]){
     const before=await page.evaluate(axis=>xyzTarget[axis],axis),button=page.locator('#xyz'+axis.toUpperCase()+'Increase');
     assert.equal(await button.locator('text').textContent(),String(amount),'Arrow label matches fine step');
     await button.click();await page.waitForFunction(()=>!pendingXYZ&&!xyzSending&&!inflight);
     const orientation=axis==='z'?1:await page.evaluate(()=>viewport.direction);
     assert(Math.abs((await page.evaluate(axis=>xyzTarget[axis],axis))-before-amount*orientation)<.001,'Fine tune uses ten times smaller '+axis+' step');
    }
    await page.locator('#xyzPrecision').click();
    for(const size of [{width:390,height:844},{width:844,height:390},{width:667,height:320}]){
     await page.setViewportSize(size);await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
     await page.waitForFunction(()=>document.getElementById('xyzZ').getBoundingClientRect().height>20);
     await page.screenshot({path:`/tmp/xyz-${team}-${mode}-${size.width}.png`});
     const ids=['xyzZIncrease','xyzZ','xyzZDecrease',...(mode==='xyz'?['xyzXDecrease','xyzX','xyzXIncrease','xyzYDecrease','xyzY','xyzYIncrease']:[])];
     const boxes=await page.evaluate(ids=>ids.map(id=>{const r=document.getElementById(id).getBoundingClientRect();return {id,x:r.x,y:r.y,w:r.width,h:r.height};}),ids);
     for(const b of boxes)assert(b.x>=0&&b.y>=0&&b.x+b.w<=size.width+.5&&b.y+b.h<=size.height+.5,JSON.stringify({team,mode,size,b}));
     for(const rail of [['xyzZIncrease','xyzZ','xyzZDecrease'],...(mode==='xyz'?[['xyzYDecrease','xyzY','xyzYIncrease']]:[])]){
      const [a,b,c]=rail.map(id=>boxes.find(x=>x.id===id));assert(a.y+a.h<=b.y+.5&&b.y+b.h<=c.y+.5,'Vertical arrows do not overlap the slider');
     }
    }
    await page.setViewportSize({width:390,height:844});
    verified.push(team+' '+mode+' increments and layouts');
   }
  }
  // Reconnect directly in XYZ as well as preserving an existing Joint session.
  await gm.locator('#testMobileControl').selectOption('2');await gm.locator('#applyTestUnlocks').click();
  for(const {team,page} of players){
   await page.waitForFunction(()=>controlMode==='xyz'&&available());await page.locator('#stop').click();
   await page.waitForFunction(()=>!session&&!document.getElementById('connect').disabled);
   await page.locator('#connect').click();await page.waitForFunction(()=>session&&available());
   verified.push(team+' explicit reconnect in XYZ');
   const ended=await page.evaluate(()=>{
    applyState({...state,phase:'overrun',server_time:Date.now()/1000});
    return {disabled:document.getElementById('connect').disabled,message:document.getElementById('feedback').textContent};
   });
   assert(ended.disabled);assert.match(ended.message,/Game ended.*Reset/,'Ended games explain why Connect is blocked');
  }
  await gm.request.post(origin+'/__test/camera',{data:{enabled:false}});
  for(const [control,mode] of [[2,'xyz'],[3,'targeting'],[4,'cue']]){
   await gm.request.post(origin+'/__test/command',{data:{action:'virtual_test_loadout',levels:null,control}});
   for(const {team,page} of players){
    await page.waitForFunction(m=>state?.virtual_play&&controlMode===m,mode);
    if(!await page.evaluate(()=>!!session))await page.locator('#connect').click();
    await page.waitForFunction(()=>available());
    for(const [axis,step] of [['z',1],...(mode==='xyz'?[['x',10],['y',10]]:[])]){
     const before=await page.evaluate(axis=>xyzTarget[axis],axis);
     await page.locator('#xyz'+axis.toUpperCase()+'Increase').click();
     await page.waitForFunction(()=>!pendingXYZ&&!xyzSending&&!inflight);
     const orientation=axis==='z'?1:await page.evaluate(()=>viewport.direction);
     assert(Math.abs((await page.evaluate(axis=>xyzTarget[axis],axis))-before-step*orientation)<.01,team+' virtual '+mode+' '+axis);
    }
    verified.push(team+' virtual '+mode+' increments');
   }
  }
  assert.deepEqual(errors,[]);console.log(JSON.stringify({verified,errors}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
