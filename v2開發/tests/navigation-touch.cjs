const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{const b=await chromium.launch({channel:'msedge',headless:true});try{
for(const width of [390,412]){
const c=await b.newContext({viewport:{width,height:844},hasTouch:true,isMobile:true,serviceWorkers:'block'});
let recordCalls=0;
await c.route('**/*',route=>{const u=new URL(route.request().url());if(u.pathname==='/api/me')return route.fulfill({json:{email:'fixture@example.test',name:'Fixture',is_premium:false}});if(u.pathname==='/api/get_memories'){recordCalls++;return new Promise(resolve=>setTimeout(resolve,100)).then(()=>route.fulfill({json:[]}));}if(u.hostname!=='127.0.0.1')return route.abort();return route.continue()});
const p=await c.newPage();await p.goto('http://127.0.0.1:8002/index.html');await p.waitForTimeout(500);
recordCalls=0;
await p.evaluate(()=>Promise.all([fetch('/api/get_memories?t=1').then(r=>r.json()),fetch('/api/get_memories?t=2').then(r=>r.json())]));
assert.equal(recordCalls,1);
await p.evaluate(()=>fetch('/api/get_memories?t=3').then(r=>r.json()));assert.equal(recordCalls,2);
console.log('PASS in-flight record requests shared without stale cache');
await p.evaluate(()=>{
 const target=document.body,t=(x,y)=>new Touch({identifier:1,target,clientX:x,clientY:y});
 window.dispatchEvent(new TouchEvent('touchstart',{touches:[t(180,200)]}));
 window.dispatchEvent(new TouchEvent('touchmove',{touches:[t(184,320)]}));
 window.dispatchEvent(new TouchEvent('touchend',{changedTouches:[t(184,320)]}));
});
assert.equal(await p.locator('#swipeWrapper').evaluate(el=>el.style.transform),'translateX(-'+width+'px)');
assert.equal(await p.locator('#dragOverlay').evaluate(el=>getComputedStyle(el).pointerEvents),'none');
console.log('PASS '+width+'px vertical swipe does not move shell');
const gesture=await p.evaluate(()=>{
 const frame=document.querySelector('iframe[src="home.html"]'), win=frame.contentWindow;
 const positions=[];
 for(const direction of [-1,1]) {
  goToPage(1,false);
  const emit=(type,x)=>{const rect=frame.getBoundingClientRect(),target=win.document.body;
   const t=new win.Touch({identifier:7,target,clientX:x-rect.left,clientY:200-rect.top});
   target.dispatchEvent(new win.TouchEvent(type,{touches:type==='touchend'?[]:[t],changedTouches:[t],bubbles:true}));};
  emit('touchstart',200);
  for(let step=1;step<=10;step++){emit('touchmove',200+direction*step*5);positions.push([parseFloat(swipeWrapper.style.transform.slice(11)), -innerWidth+(step<3?0:direction*step*5)]);}
  emit('touchend',200+direction*50);
 }
 goToPage(1,false);return positions;
});
for(const [actual,expected] of gesture)assert.ok(Math.abs(actual-expected)<0.1,`moving iframe ${actual} != ${expected}`);
console.log('PASS slow left/right moving iframe coordinates remain stable');
const cache=await p.evaluate(async()=>{
 await FoodiemoSessionReady;
 FoodiemoViewCache.write('records',[{id:'cached'}]);
 const seen=[];await loadFoodiemoRecords(data=>seen.push(data));
 FoodiemoViewCache.write('month','2025-01-01');
 localStorage.setItem('myProfileEmail','other@example.test');
 const isolated=FoodiemoViewCache.read('month')===null;
 localStorage.setItem('myProfileEmail','fixture@example.test');
 FoodiemoViewCache.clear();
 return {seen,isolated,cleared:FoodiemoViewCache.read('month')===null};
});
assert.deepEqual(cache.seen,[[{id:'cached'}],[]]);assert.ok(cache.isolated&&cache.cleared);
console.log('PASS cached data renders first, server empty replaces it, account isolation and clearing');
const pencil=p.frameLocator('iframe[src="home.html"]').locator('a[href="edit.html?from=home"]');
await pencil.evaluate(el=>{const t=new Touch({identifier:1,target:el,clientX:300,clientY:750});el.dispatchEvent(new TouchEvent('touchstart',{touches:[t],changedTouches:[t],bubbles:true}));});
assert.equal(await p.locator('#dragOverlay').evaluate(el=>getComputedStyle(el).pointerEvents),'none');
await pencil.tap();await p.waitForURL('**/edit.html?from=home');assert.equal(await p.locator('#shareBtn').innerText(),'Finish');
assert.equal(await p.locator('#choosePhotosBtn').isVisible(),true);
const chooserEvent=p.waitForEvent('filechooser');await p.locator('#choosePhotosBtn').tap();
const chooser=await chooserEvent;
assert.equal(chooser.isMultiple(),true);
await chooser.setFiles(require('path').resolve(__dirname,'../frontend/IMG_1940.jpg'));
await p.waitForSelector('#feedGrid .grid-item img');
const stable=await p.evaluate(()=>{const before=createdUrls.size;handleGridClick(0);handleGridClick(0);return createdUrls.size===before;});
assert.equal(stable,true);console.log('PASS '+width+'px album chooser, thumbnail and reused preview');
p.once('dialog',d=>d.accept());await p.locator('#backBtn').tap();await p.waitForURL('**/index.html');console.log('PASS '+width+'px pencil tap, no overlay interception, editor and Back');
await c.close();
}}finally{await b.close()}})().catch(e=>{console.error(e.message);process.exitCode=1});
