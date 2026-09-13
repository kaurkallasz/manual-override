// Run virtual_upgrades_fixture.py first. All commands target its temporary game.
const assert = require('node:assert/strict'), fs = require('node:fs');
const {chromium} = require('playwright');
const origin = 'http://127.0.0.1:' + fs.readFileSync('/tmp/virtual-upgrades-port','utf8');
(async () => {
  const browser = await chromium.launch({headless:true, executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  const errors = [];
  try {
    const page = await browser.newPage({viewport:{width:1800,height:1200}});
    page.on('pageerror', e => errors.push(e.message));
    await page.addInitScript(() => {
      let api;
      Object.defineProperty(window,'TowerDefenceView',{get:()=>api,set(value){
        api=value;const create=value.create;
        value.create=options=>create({...options,onAssetStatus:s=>{window.assetStatus=s;options.onAssetStatus?.(s);}});
      }});
    });
    await page.goto(origin+'/s/gamemaster/p/laser-tag-y/game');
    await page.waitForFunction(()=>ui.state?.status==='ready');
    await page.evaluate(async () => {
      await command({action:'reset'});
      await command({action:'set_virtual',virtual_play:true});
    });
    await page.click('#maxTestUnlocks');
    await page.waitForFunction(()=>ui.state.virtual_test_loadout?.forcefield===4);
    await page.evaluate(async () => {
      for (const [i,s] of ui.state.level.sockets.entries())
        await command({action:'place',atom_tag_id:100+i%4,socket_id:s.socket_id});
    });
    await page.waitForFunction(()=>ui.state.companions?.length===12 && ui.state.companions.every(t=>t.operational));
    await page.waitForFunction(()=>window.assetStatus?.loaded>0 && window.assetStatus.pending===0);
    assert.equal(await page.evaluate(()=>assetStatus.failed),0);
    assert.deepEqual(await page.evaluate(()=>ui.state.towers.filter(t=>!ui.state.companions.some(c=>c.parent_placement_id===t.placement_id)).map(t=>t.aruco_id).sort()),[47,48,50,54]);
    const bounds = await page.evaluate(() => {
      const draw = CanvasRenderingContext2D.prototype.drawImage;
      let layers=[];
      CanvasRenderingContext2D.prototype.drawImage=function(image,...args){
        if(this.canvas.id==='gameCanvas' && image instanceof HTMLCanvasElement && image.width===256)
          layers.push({image,args,m:this.getTransform()});
        return draw.call(this,image,...args);
      };
      const scene=structuredClone(ui.state), units=[...scene.towers,...scene.companions];
      // A fixed, server-derived scene lets every aiming direction be checked in one frame.
      scene.paused=true;scene.phase='running';scene.sim_time=100;
      units.forEach(t=>{t.last_fire_at=-100;t.weapon_charge=0;t.targeting.half_angle=0;});
      let checked=0, maximumExtent=0;
      for(let angle=0;angle<8;angle++){
        for(const t of units){t.targeting.angle=angle*Math.PI/4;t.placement_id=`${t.socket_id}:${t.is_companion?'c':'p'}:${angle}`;}
        ui.view.applyState(scene);layers=[];ui.view.renderGame(performance.now());
        if(layers.length!==56)throw Error(`Expected 56 art layers, got ${layers.length}`);
        for(const [i,t] of units.entries()){
          const socket=scene.level.sockets.find(s=>s.socket_id===t.socket_id);
          const x=t.is_companion?t.visual_x:t.x, y=t.is_companion?t.visual_y:socket.marker_y;
          const half=t.is_companion?48:56;
          for(const layer of layers.slice(i*2,i*2+2)){
            const data=layer.image.getContext('2d').getImageData(0,0,256,256).data;
            const [dx,dy,w,h]=layer.args,m=layer.m;
            for(let p=0;p<data.length;p+=4){
              if(data[p+3]<32)continue;
              const sx=dx+(p/4%256+.5)/256*w,sy=dy+(Math.floor(p/4/256)+.5)/256*h;
              const wx=m.a*sx+m.c*sy+m.e,wy=m.b*sx+m.d*sy+m.f;
              const extent=Math.max(Math.abs(wx-x),Math.abs(wy-y));
              maximumExtent=Math.max(maximumExtent,extent/half);
              if(extent>half)throw Error(`${t.socket_id}: art outside pod at angle ${angle}`);
            }
          }
          checked++;
        }
      }
      CanvasRenderingContext2D.prototype.drawImage=draw;
      ui.view.applyState(ui.state);
      return {checked, maximumExtent};
    });
    assert.equal(bounds.checked,224);
    const companion = await page.evaluate(()=>ui.state.companions[0]);
    await page.locator('#gameCanvas').scrollIntoViewIfNeeded();
    const canvas = await page.locator('#gameCanvas').boundingBox();
    await page.mouse.click(canvas.x+companion.visual_x*canvas.width/1696,canvas.y+companion.visual_y*canvas.height/960);
    await page.waitForFunction(id=>ui.selectedTower===id,companion.parent_placement_id);
    await page.evaluate(()=>setAimDraft(25,.65,false));
    await page.evaluate(()=>saveAim());
    await page.waitForFunction(()=>Math.abs(ui.state.companions[0].targeting.angle_degrees-25)<.01);
    await page.locator('#gameCanvas').evaluate(e=>e.parentElement.setAttribute('data-preview','map'));
    await page.locator('[data-preview="map"]').screenshot({path:'/tmp/companions-game.png'});
    const screen = await browser.newPage({viewport:{width:1696,height:960}});
    screen.on('pageerror',e=>errors.push(e.message));
    await screen.addInitScript(() => {
      let api;
      Object.defineProperty(window,'TowerDefenceView',{get:()=>api,set(value){
        api=value;const create=value.create;
        value.create=options=>create({...options,onAssetStatus:s=>{window.assetStatus=s;options.onAssetStatus?.(s);}});
      }});
    });
    await screen.goto(origin+'/s/gamemaster/p/laser-tag-y/screen');
    await screen.waitForFunction(()=>typeof view!=='undefined' && view?.levelReady && window.assetStatus?.loaded>0 && window.assetStatus.pending===0);
    assert.equal(await screen.evaluate(()=>assetStatus.failed),0);
    await screen.screenshot({path:'/tmp/companions-screen.png'});
    await page.selectOption('[data-test-track="damage-machine-gun"]','3');
    await page.click('#applyTestUnlocks');
    await page.waitForFunction(()=>ui.state.companions.length===9);
    await page.click('#maxTestUnlocks');
    await page.waitForFunction(()=>ui.state.companions.length===12);
    await page.reload();await page.waitForFunction(()=>ui.state?.companions?.length===12);
    await page.click('#reset');await page.waitForFunction(()=>ui.state.towers.length===0 && ui.state.companions.length===0);
    assert.deepEqual(errors,[]);
    console.log('Companion browser checks passed:',JSON.stringify({bounds,errors,views:2,units:28}));
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
