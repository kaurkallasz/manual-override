'use strict';
const assert=require('node:assert/strict');
const Viewport=require('../shared/mobile_ltz/viewport.js');
const v=new Viewport();v.resize(852,393);
assert.equal(v.zoom,1);assert.equal(v.cx,848);
v.setZoom(20);assert.equal(v.zoom,4);
const point=v.point(400,180);v.setZoom(3,400,180);
assert.ok(Math.abs(v.point(400,180).x-point.x)<1e-8);
assert.ok(Math.abs(v.point(400,180).y-point.y)<1e-8);
v.pan(100000,-100000);
assert.ok(v.point(0,0).x>=-1e-8);assert.ok(v.point(v.vw,v.vh).y<=960+1e-8);
v.resize(393,852);assert.equal(v.zoom,3);
v.fit();assert.equal(v.zoom,1);assert.equal(v.cx,848);assert.equal(v.cy,480);
v.setZoom(-5);assert.equal(v.zoom,1);
console.log('Viewport bounds, pinch anchor, resize and Fit passed.');
const mini=new Viewport(1696,960);mini.resize(390,580);
assert.deepEqual(mini.bounds(),{x:0,y:0,width:1696,height:960});
mini.setZoom(4);mini.center(99999,-99999);
let bounds=mini.bounds();assert.ok(bounds.x+bounds.width<=mini.w+1e-8);assert.equal(bounds.y,0);
const center=[mini.cx,mini.cy];mini.center(NaN,Infinity);assert.deepEqual([mini.cx,mini.cy],center);
mini.resize(844,390);bounds=mini.bounds();assert.ok(bounds.x>=0&&bounds.y>=0&&bounds.width<=mini.w&&bounds.height<=mini.h);
mini.fit();assert.deepEqual(mini.bounds(),{x:0,y:0,width:1696,height:960});
console.log('Minimap centering and visible bounds passed, including letterboxing.');

// Corrected video and overlays retain one transform. The entire board fits,
// with surrounding camera pixels filling the sides on wide screens.
const camera=new Viewport(1280,720);
camera.resize(844,390);
const registered={status:'ready',matrix:[.6,0,.2,0,.6,.2,0,0]};
camera.setCamera(registered,true);
assert.equal(camera.zoom,1);
assert.ok(Math.abs(camera.scale*604.8-390)<1e-8,'entire board height fits');
assert.ok(Math.abs(camera.point(422,0).y-57.6)<1e-8);
assert.ok(Math.abs(camera.point(422,390).y-662.4)<1e-8);
assert.ok(camera.point(0,195).x<256,'left camera margin remains visible');
assert.ok(camera.point(844,195).x>1024,'right camera margin remains visible');
assert.ok(camera.scale*1280>camera.scale*768,'camera side margins are retained beyond the board');
camera.resize(390,844);
assert.ok(Math.abs(camera.scale*768-390)<1e-8);
const anchor=camera.point(130,410);camera.setZoom(2,130,410);
assert.ok(Math.abs(camera.point(130,410).x-anchor.x)<1e-8);
const stable=[camera.cx,camera.cy,camera.zoom,camera.scale];
camera.setCamera({status:'ready',matrix:[.61,0,.19,0,.8,.1,0,0]});
assert.deepEqual([camera.cx,camera.cy,camera.zoom,camera.scale],stable);
camera.setCamera({status:'unavailable'});
assert.deepEqual([camera.cx,camera.cy,camera.zoom,camera.scale],stable);
camera.setCamera(null,true);
assert.equal(camera.cameraFrame,null);
assert.equal(camera.scale,Math.min(390/1280,844/720));
for(const matrix of [null,[],[1,0,0,0,1,0,-2,0],[NaN,0,0,0,1,0,0,0],[0,0,0,0,0,0,0,0]]){
 camera.setCamera({status:'ready',matrix},true);
 assert.equal(camera.cameraAligned,false);
 assert.equal(camera.scale,Math.min(390/1280,844/720),'missing registration shows the full camera');
}
camera.setCamera(registered);
assert.equal(camera.cameraAligned,true,'first valid registration replaces the fallback crop');
console.log('Whole-board fit, uncropped side margins, overlay coordinates, rotation, stability and fallback passed.');

// Registration loss must not alternate the view between level and camera sizes.
const live=new Viewport();live.resize(844,390);
const scene={run_id:'one',level_revision:1,virtual_play:false,level:{name:'Board',width:1696,height:960},mobile_camera:{...registered,width:2560,height:1440}};
live.configure(scene);live.setZoom(1.4);live.pan(20,10);
const held={w:live.w,h:live.h,cx:live.cx,cy:live.cy,zoom:live.zoom,css:live.css()};
for(let i=0;i<10;i++){
 live.configure({...scene,mobile_camera:{status:'unavailable',error:'Markers hidden'}});
 assert.deepEqual({w:live.w,h:live.h,cx:live.cx,cy:live.cy,zoom:live.zoom,css:live.css()},held);
 live.configure(scene);
 assert.equal(live.css(),held.css);
}
live.configure({...scene,virtual_play:true});assert.equal(live.w,1696);assert.equal(live.h,960);assert.equal(live.cameraFrame,null);assert.equal(live.zoom,1);
live.configure(scene);assert.equal(live.w,2560);assert.equal(live.cameraAligned,true);
live.configure({...scene,mobile_camera:{...scene.mobile_camera,width:1280,height:720}});assert.equal(live.w,1280);assert.equal(live.zoom,1);
console.log('Tracking dropouts preserve camera dimensions, framing and manual zoom; real mode/size changes reframe.');

// Rotation must reverse display and input once, while preserving canonical calibration.
const opposite=new Viewport(1000,600);opposite.resize(844,390);
opposite.setZoom(2);opposite.center(540,310);
const before=opposite.screen(250,210),original=opposite.bounds();
opposite.setRotation(180);const after=opposite.screen(250,210);
assert.ok(Math.abs(after.x-(opposite.vw-before.x))<1e-8);
assert.ok(Math.abs(after.y-(opposite.vh-before.y))<1e-8);
assert.deepEqual(opposite.point(after.x,after.y),{x:250,y:210});
assert.deepEqual(opposite.bounds(),original);
const locked=opposite.point(300,180);opposite.setZoom(2.5,300,180);
assert.ok(Math.abs(opposite.point(300,180).x-locked.x)<1e-8);
assert.ok(Math.abs(opposite.point(300,180).y-locked.y)<1e-8);
const panStart=opposite.screen(500,300);opposite.pan(12,-9);const panEnd=opposite.screen(500,300);
assert.ok(Math.abs(panEnd.x-panStart.x-12)<1e-8);assert.ok(Math.abs(panEnd.y-panStart.y+9)<1e-8);
opposite.fit();opposite.resize(390,844);
assert.deepEqual(opposite.bounds(),{x:0,y:0,width:1000,height:600});
assert.match(opposite.css(),/rotate\(180deg\)/);
opposite.setRotation(0);assert.match(opposite.css(),/rotate\(0deg\)/);
console.log('180-degree video/overlay projection, inverse touch mapping, pinch anchor, pan direction and portrait bounds passed.');

// Entering calibration on the same map/run resets the latched game crop.
const lesson=new Viewport();lesson.resize(390,844);
const lessonScene={run_id:'same',level_revision:1,level:{name:'board',width:1696,height:960},virtual_play:false,mobile_camera:{...registered,width:1280,height:720}};
lesson.configure(lessonScene);const boardFrame={...lesson.cameraFrame};lesson.setZoom(2);
lesson.configure({...lessonScene,journey:{phase:'calibration',id:'lesson'},mobile_camera:{...lessonScene.mobile_camera,matrix:[1,0,0,0,1,0,0,0]}});
assert.deepEqual(lesson.cameraFrame,{x:0,y:0,width:1280,height:720});assert.equal(lesson.zoom,1);
lesson.configure(lessonScene);assert.deepEqual(lesson.cameraFrame,boardFrame);
console.log('Calibration replaces the game crop and restores it when the lesson ends.');
