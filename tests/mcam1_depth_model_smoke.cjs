// Optional network smoke: real public model, local inference, no robot requests.
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const {chromium}=require('playwright');
const source=fs.readFileSync(path.join(__dirname,'../sandboxes/gamemaster/prototypes/mcam1-depth/web/app.js'),'utf8').split('\n(() => {')[0];
(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  try{
    const page=await browser.newPage({viewport:{width:960,height:640}});
    page.on('console',message=>{if(message.type()==='log')console.log(message.text());});
    page.on('pageerror',error=>console.error(error.message));
    await page.route('http://127.0.0.1:9876/',route=>route.fulfill({contentType:'text/html',body:'<canvas id="output" width="480" height="320" style="width:960px"></canvas>'}));
    await page.goto('http://127.0.0.1:9876/');await page.addScriptTag({content:source});
    const preview=process.env.MCAM1_DEPTH_FRAME?'data:image/jpeg;base64,'+fs.readFileSync(process.env.MCAM1_DEPTH_FRAME).toString('base64'):null;
    const result=await page.evaluate(async ({preview,forceCPU})=>{
      if(!preview){const c=document.getElementById('output'),g=c.getContext('2d');g.fillStyle='#c8c4bc';g.fillRect(0,0,480,320);g.fillStyle='#405e90';g.fillRect(60,80,150,180);g.fillStyle='#c56c40';g.fillRect(320,150,60,80);preview=c.toDataURL();}
      return await new Promise((resolve,reject)=>{
        const started=performance.now(),worker=new Worker(URL.createObjectURL(new Blob(['('+DepthBricks.workerMain.toString()+')('+forceCPU+')'],{type:'text/javascript'})),{type:'module'});
        worker.onerror=e=>reject(Error(e.message));
        worker.onmessage=({data})=>{
          if(data.type==='loading'&&(data.progress===0||data.progress===100))console.log(JSON.stringify(data));
          if(data.type==='error'){worker.terminate();reject(Error(data.error));}
          if(data.type==='ready'){console.log(JSON.stringify(data));worker.postMessage({id:1,preview});}
          if(data.type==='result'){
            const points=DepthBricks.relativePoints(data.values,data.width,data.height,480,320),map=DepthBricks.grid(points,480,320,12,true);
            DepthBricks.paint(document.getElementById('output').getContext('2d'),map,480,320,0,1);
            worker.terminate();resolve({width:data.width,height:data.height,cells:map.cells.length,min:Math.min(...points.map(p=>p.relative_depth)),max:Math.max(...points.map(p=>p.relative_depth)),seconds:(performance.now()-started)/1000});
          }
        };
      });
    },{preview,forceCPU:process.env.MCAM1_DEPTH_CPU==='1'});
    assert(result.cells>200);assert(result.max-result.min>.7);console.log(JSON.stringify(result));
    await page.screenshot({path:path.join(__dirname,'../output/mcam1-depth-2026-10-19/real-model-preview.png')});
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
