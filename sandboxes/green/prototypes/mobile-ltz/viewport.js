(function(root){
'use strict';
class Viewport {
  constructor(w=1696,h=960){this.w=w;this.h=h;this.vw=w;this.vh=h;this.zoom=1;this.cx=w/2;this.cy=h/2;}
  resize(w,h){this.vw=Math.max(1,w);this.vh=Math.max(1,h);this.clamp();}
  get scale(){return Math.min(this.vw/this.w,this.vh/this.h)*this.zoom;}
  clamp(){const sx=Math.min(this.w/2,this.vw/(2*this.scale)),sy=Math.min(this.h/2,this.vh/(2*this.scale));this.cx=Math.max(sx,Math.min(this.w-sx,this.cx));this.cy=Math.max(sy,Math.min(this.h-sy,this.cy));}
  point(x,y){return{x:(x-this.vw/2)/this.scale+this.cx,y:(y-this.vh/2)/this.scale+this.cy};}
  setZoom(z,x=this.vw/2,y=this.vh/2){const p=this.point(x,y);this.zoom=Math.max(1,Math.min(4,z));this.cx=p.x-(x-this.vw/2)/this.scale;this.cy=p.y-(y-this.vh/2)/this.scale;this.clamp();}
  pan(dx,dy){this.cx-=dx/this.scale;this.cy-=dy/this.scale;this.clamp();}
  center(x,y){if(Number.isFinite(x)&&Number.isFinite(y)){this.cx=x;this.cy=y;this.clamp();}}
  bounds(){const a=this.point(0,0),b=this.point(this.vw,this.vh);return {x:Math.max(0,a.x),y:Math.max(0,a.y),width:Math.min(this.w,b.x)-Math.max(0,a.x),height:Math.min(this.h,b.y)-Math.max(0,a.y)};}
  fit(){this.zoom=1;this.cx=this.w/2;this.cy=this.h/2;this.clamp();}
  css(){return `translate(${this.vw/2-this.cx*this.scale}px,${this.vh/2-this.cy*this.scale}px) scale(${this.scale})`;}
}
root.MobileViewport=Viewport;if(typeof module!=='undefined')module.exports=Viewport;
})(typeof window==='undefined'?globalThis:window);
