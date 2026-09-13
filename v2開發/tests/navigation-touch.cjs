const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{const b=await chromium.launch({channel:'msedge',headless:true});try{
for(const width of [390,412]){
const c=await b.newContext({viewport:{width,height:844},hasTouch:true,isMobile:true,serviceWorkers:'block'});
await c.route('**/*',route=>{const u=new URL(route.request().url());if(u.pathname==='/api/me')return route.fulfill({json:{email:'fixture@example.test',name:'Fixture',is_premium:false}});if(u.pathname==='/api/get_memories')return route.fulfill({json:[]});if(u.hostname!=='127.0.0.1')return route.abort();return route.continue()});
const p=await c.newPage();await p.goto('http://127.0.0.1:8002/index.html');await p.waitForTimeout(500);
const pencil=p.frameLocator('iframe[src="home.html"]').locator('a[href="edit.html?from=home"]');
await pencil.evaluate(el=>{const t=new Touch({identifier:1,target:el,clientX:300,clientY:750});el.dispatchEvent(new TouchEvent('touchstart',{touches:[t],changedTouches:[t],bubbles:true}));});
assert.equal(await p.locator('#dragOverlay').evaluate(el=>getComputedStyle(el).pointerEvents),'none');
await pencil.tap();await p.waitForURL('**/edit.html?from=home');assert.equal(await p.locator('#shareBtn').innerText(),'Finish');
await p.locator('#backBtn').tap();await p.waitForURL('**/index.html');console.log('PASS '+width+'px pencil tap, no overlay interception, editor and Back');
await c.close();
}}finally{await b.close()}})().catch(e=>{console.error(e.message);process.exitCode=1});
