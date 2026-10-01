(function(root){
'use strict';
class Viewport {
  constructor(w=1696,h=960){this.w=w;this.h=h;this.vw=w;this.vh=h;this.zoom=1;this.cx=w/2;this.cy=h/2;this.cameraFrame=null;this.cameraAligned=false;this.rotation=0;}
  get direction(){return this.rotation===180?-1:1;}
  setRotation(degrees){this.rotation=degrees===180?180:0;}
  configure(scene){
    const {level,mobile_camera:camera}=scene,physical=!scene.virtual_play;
    if(!physical&&level){this.w=level.width;this.h=level.height;}
    else if(Number.isFinite(camera?.width)&&camera.width>0&&Number.isFinite(camera?.height)&&camera.height>0){this.w=camera.width;this.h=camera.height;}
    else if(!this.cameraFrame&&level){this.w=level.width;this.h=level.height;}
    // Losing ArUco registration does not change the camera dimensions or pose.
    const key=JSON.stringify([scene.run_id,scene.level_revision,level?.name,physical,scene.journey?.phase==='calibration'?scene.journey.id:null,this.w,this.h]);
    if(key!==this.sceneKey){this.sceneKey=key;this.setCamera(physical?camera:null,true);}
    else if(physical)this.setCamera(camera);
  }
  resize(w,h){this.vw=Math.max(1,w);this.vh=Math.max(1,h);this.clamp();}
  get scale(){return (this.cameraFrame?Math.min(this.vw/this.cameraFrame.width,this.vh/this.cameraFrame.height):Math.min(this.vw/this.w,this.vh/this.h))*this.zoom;}
  clamp(){const sx=Math.min(this.w/2,this.vw/(2*this.scale)),sy=Math.min(this.h/2,this.vh/(2*this.scale));this.cx=Math.max(sx,Math.min(this.w-sx,this.cx));this.cy=Math.max(sy,Math.min(this.h-sy,this.cy));}
  point(x,y){return{x:this.direction*(x-this.vw/2)/this.scale+this.cx,y:this.direction*(y-this.vh/2)/this.scale+this.cy};}
  screen(x,y){return{x:this.vw/2+this.direction*(x-this.cx)*this.scale,y:this.vh/2+this.direction*(y-this.cy)*this.scale};}
  setZoom(z,x=this.vw/2,y=this.vh/2){const p=this.point(x,y);this.zoom=Math.max(1,Math.min(4,z));this.cx=p.x-this.direction*(x-this.vw/2)/this.scale;this.cy=p.y-this.direction*(y-this.vh/2)/this.scale;this.clamp();}
  pan(dx,dy){this.cx-=this.direction*dx/this.scale;this.cy-=this.direction*dy/this.scale;this.clamp();}
  center(x,y){if(Number.isFinite(x)&&Number.isFinite(y)){this.cx=x;this.cy=y;this.clamp();}}
  bounds(){const a=this.point(0,0),b=this.point(this.vw,this.vh),x=Math.max(0,Math.min(a.x,b.x)),y=Math.max(0,Math.min(a.y,b.y));return {x,y,width:Math.min(this.w,Math.max(a.x,b.x))-x,height:Math.min(this.h,Math.max(a.y,b.y))-y};}
  // Fit the whole board while retaining camera pixels around it at the sides.
  // Transform the camera and every overlay together. Latch the initial registration
  // so noisy marker updates never move the view during a player gesture.
  setCamera(camera,reset=false){
    if(reset){this.cameraFrame=null;this.cameraAligned=false;}
    if(camera===null){this.fit();return;}
    if(this.cameraAligned)return;
    const h=camera?.matrix;
    let frame=null;
    if(camera?.status==='ready'&&Array.isArray(h)&&h.length===8&&h.every(Number.isFinite)){
      const points=[[0,0],[1,0],[1,1],[0,1]].map(([x,y])=>{
        const d=h[6]*x+h[7]*y+1;
        return d>1e-6?{x:(h[0]*x+h[1]*y+h[2])/d,y:(h[3]*x+h[4]*y+h[5])/d}:null;
      });
      if(points.every(p=>p&&Number.isFinite(p.x)&&Number.isFinite(p.y))){
        const left=Math.max(0,Math.min(...points.map(p=>p.x))),right=Math.min(1,Math.max(...points.map(p=>p.x)));
        // The registered game rectangle sits inside the printed board. Retain
        // the outer marker rows and board border above and below it.
        const top=Math.max(0,Math.min(...points.map(p=>p.y))-.12),bottom=Math.min(1,Math.max(...points.map(p=>p.y))+.12);
        if(right-left>.1&&bottom-top>.1)frame={x:left*this.w,y:top*this.h,width:(right-left)*this.w,height:(bottom-top)*this.h};
      }
    }
    if(frame){this.cameraFrame=frame;this.cameraAligned=true;this.fit();}
    else if(!this.cameraFrame){this.cameraFrame={x:0,y:0,width:this.w,height:this.h};this.fit();}
  }
  fit(){this.zoom=1;const f=this.cameraFrame;this.cx=f?f.x+f.width/2:this.w/2;this.cy=f?f.y+f.height/2:this.h/2;this.clamp();}
  css(){return `translate(${this.vw/2}px,${this.vh/2}px) rotate(${this.rotation}deg) scale(${this.scale}) translate(${-this.cx}px,${-this.cy}px)`;}
}
root.MobileViewport=Viewport;if(typeof module!=='undefined')module.exports=Viewport;
})(typeof window==='undefined'?globalThis:window);
