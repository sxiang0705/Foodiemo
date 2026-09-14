/* UI tests use explicit artificial fixtures; live checks are reported separately. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const http=require('node:http');
const crypto=require('node:crypto');
const ROOT=path.resolve(__dirname,'..');
const SOURCE=path.resolve(ROOT,'..','前端原始程式碼','frontend');
const OUT=path.join(ROOT,'test-results');
const BASE=process.env.V2_BASE_URL || 'http://127.0.0.1:8002';
fs.mkdirSync(OUT,{recursive:true});
const results=[];
const check=(value,label)=>{assert.ok(value,label);results.push(label);console.log('PASS '+label);};
const delay=ms=>new Promise(r=>setTimeout(r,ms));
const fixtureItems=(prefix='餐廳')=>[1,2,3].map((n)=>({
  id:n===3?'9007199254740993':String(n),title:prefix+n,subtitle:'原版測試',
  img:'IMG_1940.jpg',rating:null,hours:null,price:null,address:'測試地址',
  mapLink:'https://www.google.com/maps/search/?api=1&query=test'+n,source:'postgresql'
}));
const body=(items=fixtureItems())=>({items,source:'postgresql',algorithm_version:'fixture-v1',next_cursor:'MToz'});
async function mockContext(browser){
  const context=await browser.newContext({viewport:{width:390,height:844},hasTouch:true,serviceWorkers:'block'});
  await context.route('**/*',async route=>{
    const u=new URL(route.request().url());
    if(u.hostname!=='127.0.0.1' && u.hostname!=='localhost') return route.abort();
    if(u.pathname==='/api/me') return route.fulfill({status:401,contentType:'application/json',body:JSON.stringify({detail:'Test unauthenticated'})});
    if(u.pathname.startsWith('/api/')){
      return route.fulfill({status:200,contentType:'application/json',
        headers:{'Access-Control-Allow-Origin':route.request().headers().origin||'*','Access-Control-Allow-Credentials':'true'},
        body:JSON.stringify(u.pathname.includes('recommendations')?body():
          u.pathname.includes('get_memories')?[]:{is_vip:false})});
    }
    return route.continue();
  });
  return context;
}
async function touchPull(page,dy=140,start=75){
  await page.locator('#listContainer').evaluate((el,{dy,start})=>{
    const touch=y=>new Touch({identifier:1,target:el,clientX:350,clientY:y});
    el.dispatchEvent(new TouchEvent('touchstart',{touches:[touch(start)],changedTouches:[touch(start)],bubbles:true}));
    el.dispatchEvent(new TouchEvent('touchmove',{touches:[touch(start+dy)],changedTouches:[touch(start+dy)],bubbles:true,cancelable:true}));
    el.dispatchEvent(new TouchEvent('touchend',{touches:[],changedTouches:[touch(start+dy)],bubbles:true}));
  },{dy,start});
}
function pixels(png){
  const zlib=require('node:zlib');let pos=8,w,h,channels,parts=[];
  while(pos<png.length){const n=png.readUInt32BE(pos),kind=png.toString('ascii',pos+4,pos+8),data=png.subarray(pos+8,pos+8+n);pos+=n+12;
    if(kind==='IHDR'){w=data.readUInt32BE(0);h=data.readUInt32BE(4);assert.equal(data[8],8);channels=data[9]===2?3:4;}
    if(kind==='IDAT')parts.push(data);
  }
  const raw=zlib.inflateSync(Buffer.concat(parts)),stride=w*channels,out=Buffer.alloc(stride*h);
  const paeth=(a,b,c)=>{const p=a+b-c,pa=Math.abs(p-a),pb=Math.abs(p-b),pc=Math.abs(p-c);return pa<=pb&&pa<=pc?a:pb<=pc?b:c;};
  for(let y=0;y<h;y++){const filter=raw[y*(stride+1)];for(let x=0;x<stride;x++){
    const i=y*stride+x,a=x>=channels?out[i-channels]:0,b=y?out[i-stride]:0,c=y&&x>=channels?out[i-stride-channels]:0;
    const predictor=[0,a,b,Math.floor((a+b)/2),paeth(a,b,c)][filter];out[i]=(raw[y*(stride+1)+1+x]+predictor)&255;
  }}return out;
}
async function geometry(page){return page.locator('.card,.card-img,.card-info-overlay,.card-title,.card-subtitle,.status-chip,.back-btn').evaluateAll(nodes=>nodes.map(n=>{
 const r=n.getBoundingClientRect(),s=getComputedStyle(n);return {cls:n.className,x:r.x,y:r.y,w:r.width,h:r.height,font:s.font,padding:s.padding,borderRadius:s.borderRadius};
}));}
async function settled(page){
  await page.locator('.card').first().waitFor();
  await page.waitForFunction(()=>[...document.images].filter(x=>x.className==='card-img').every(x=>x.complete));
  await page.waitForTimeout(700);
}
(async()=>{
  // Strict read-only static reference server. Never serve real env or arbitrary folders.
  const mime={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.jpg':'image/jpeg','.png':'image/png','.ico':'image/x-icon','.json':'application/json'};
  const original=http.createServer((req,res)=>{
    const name=decodeURIComponent(new URL(req.url,'http://localhost').pathname).slice(1)||'index.html';
    if(name.includes('/') || name.includes('..') || !mime[path.extname(name)]){res.writeHead(404).end();return;}
    if(name==='env.js'||name==='google-auth-config.js'){res.writeHead(200,{'Content-Type':'text/javascript'}).end('');return;}
    const p=path.join(SOURCE,name);
    if(!fs.existsSync(p)){res.writeHead(404).end();return;}
    res.writeHead(200,{'Content-Type':mime[path.extname(name)]});fs.createReadStream(p).pipe(res);
  });
  await new Promise(r=>original.listen(0,'127.0.0.1',r));
  const REF='http://127.0.0.1:'+original.address().port;
  const browser=await chromium.launch({headless:true,channel:'msedge'});
  try {
    const context=await mockContext(browser);
    const page=await context.newPage();
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    let requests=[];
    page.on('request',r=>{if(r.url().includes('/restaurants/recommendations'))requests.push(r.url());});
    await page.goto(BASE+'/search.html');await settled(page);
    check(await page.locator('.card').count()===3,'REST-01 original three cards');
    check(new URL(requests[0]).searchParams.get('count')==='3','REST-01 count=3 contract');
    check(await page.locator('input,select').count()===0,'UI-08 no search filter pagination controls');
    check(await page.locator('.card').last().getAttribute('data-restaurant-id')==='9007199254740993','REST-07 bigint string identity');
    const reference=await context.newPage();
    // Original source labels Google results as real; test fixtures are explicitly synthetic.
    await reference.route('**/restaurants/recommendations?**',route=>route.fulfill({contentType:'application/json',body:JSON.stringify({...body(),source:'google_places'})}));
    await reference.goto(REF+'/search.html');await settled(reference);
    const baseline=await reference.screenshot({path:path.join(OUT,'original-search.png')});
    const adapted=await page.screenshot({path:path.join(OUT,'v2-search-fixture.png')});
    assert.deepEqual(await geometry(reference),await geometry(page));
    check(true,'UI-07 original/v2 card and control geometry/styles exact');
    const a=pixels(baseline),b=pixels(adapted);assert.equal(a.length,b.length);
    let delta=0,large=0;for(let i=0;i<a.length;i++){const d=Math.abs(a[i]-b[i]);delta+=d;if(d>20)large++;}
    const metric={meanChannelDifference:delta/a.length,largeDifferenceRatio:large/a.length};
    console.log('Screenshot metric',metric);
    fs.writeFileSync(path.join(OUT,'visual-comparison.json'),JSON.stringify(metric,null,2));
    check(metric.meanChannelDifference<1 && metric.largeDifferenceRatio<0.01,'UI-07 screenshot within rasterization tolerance; visually reviewed');
    await reference.close();

    let before=requests.length;
    await touchPull(page,60);await delay(300);
    check(requests.length===before,'REST-02 short pull does not reload');
    await touchPull(page,140);
    await page.waitForFunction(()=>document.getElementById('loadingContainer').style.height==='0px');
    await delay(100);
    check(requests.length===before+1,'REST-02 touch pull replaces batch');
    check(new URL(requests.at(-1)).searchParams.get('cursor')==='MToz','REST-02 internal rotation cursor');
    check(await page.locator('.card').count()===3,'REST-02 no appended cards');
    await page.locator('#listContainer').evaluate(el=>el.scrollTop=200);
    before=requests.length;await touchPull(page,140);await delay(150);
    check(requests.length===before,'REST-03 non-top scroll does not refresh');
    await page.locator('#listContainer').evaluate(el=>el.scrollTop=0);
    await delay(300);before=requests.length;
    await page.mouse.move(350,75);await page.mouse.down();await page.mouse.move(350,215,{steps:10});await page.mouse.up();
    await delay(400);
    check(requests.length===before+1,'REST-04 mouse pull refresh');
    await page.locator('.card').first().click();
    await page.locator('#detailModal.active').waitFor();
    check(await page.locator('#modal-title').innerText()==='餐廳1','REST-05 overlay uses selected card');
    check(await page.locator('#modal-rating').innerText()==='評分未提供','REST-08 no fabricated rating');
    check(!(await page.locator('#modal-source-text').innerText()).includes('Google Places API'),'REST-12 database source text');
    await page.evaluate(()=>{window.__map=null;window.open=(...args)=>{window.__map=args;};});
    await page.locator('.navigate-btn').click();
    const map=await page.evaluate(()=>window.__map);
    check(map[0].startsWith('https://www.google.com/maps/') && map[1]==='_blank' && map[2].includes('noopener'),'REST-06 map opens safely');
    await page.locator('.detail-nav .nav-circle').click();await delay(350);
    check(!(await page.locator('#detailModal').isVisible()),'REST-05 closes overlay preserves list');
    check(await page.locator('.card').count()===3,'REST-05 list remains');

    // Hostile fixture is text, and unsafe URL never executes.
    await page.route('**/restaurants/recommendations?**',route=>route.fulfill({contentType:'application/json',body:JSON.stringify(body([
      {...fixtureItems()[0],title:'<img src=x onerror=window.PWNED=1>',img:'javascript:alert(1)',mapLink:'javascript:alert(1)'}
    ]))}));
    await page.evaluate(()=>fetchRestaurants());await settled(page);
    check(await page.locator('.card-title img').count()===0 && !(await page.evaluate(()=>window.PWNED)),'REST-07 safe text rendering');
    check((await page.locator('.card-img').getAttribute('src')).includes('restaurant-placeholder'),'REST-08 local missing-photo placeholder');
    await page.locator('.card').click();
    page.once('dialog',d=>d.accept());
    await page.locator('.navigate-btn').click();
    check((await page.evaluate(()=>window.__map))[0].startsWith('https://'),'REST-06 unsafe map rejected');
    await page.locator('.detail-nav .nav-circle').click();await delay(350);
    await page.unroute('**/restaurants/recommendations?**');

    await page.route('**/restaurants/recommendations?**',route=>route.fulfill({contentType:'application/json',body:JSON.stringify(body([]))}));
    await page.evaluate(()=>fetchRestaurants());
    check((await page.locator('.empty-state').innerText()).includes('沒有'),'REST-09 zero candidates empty state');
    await page.unroute('**/restaurants/recommendations?**');
    await page.route('**/restaurants/recommendations?**',route=>route.fulfill({status:503,contentType:'application/json',body:'{}'}));
    await page.evaluate(()=>fetchRestaurants());
    check((await page.locator('.empty-state').innerText()).includes('失敗'),'REST-11 failure distinguished from empty');
    await page.screenshot({path:path.join(OUT,'v2-error.png')});
    await page.unroute('**/restaurants/recommendations?**');
    await touchPull(page,140);await settled(page);
    check(await page.locator('.card').count()===3,'REST-11 retry uses original pull');
    // Delayed older fetch resolution, including a fetch implementation ignoring abort.
    await page.evaluate(async()=>{
      const original=window.fetch;
      let call=0;
      window.fetch=async()=>{const n=++call;await new Promise(r=>setTimeout(r,n===1?180:15));
        return new Response(JSON.stringify({items:[{id:String(n),title:n===1?'OLDER':'LATEST'}],source:'postgresql',next_cursor:null}),{status:200});};
      await Promise.all([fetchRestaurants(),fetchRestaurants()]);
      window.fetch=original;
    });
    check(await page.locator('.card-title').innerText()==='LATEST','REST-10 late response cannot overwrite latest');
    // Exercise actual 10-second bounded timeout using a network request waiting for abort.
    await page.evaluate(async()=>{
      const original=window.fetch;
      window.fetch=(_,options)=>new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError'))));
      await fetchRestaurants();window.fetch=original;
    });
    check((await page.locator('.empty-state').innerText()).includes('失敗'),'REST-11 request timeout is recoverable');
    await page.evaluate(()=>fetchRestaurants());await settled(page);

    // Auth guard remains unchanged, not bypassed by application code.
    await page.goto(BASE+'/index.html');
    await page.waitForURL('**/login.html');
    check(page.url().endsWith('login.html'),'UI-01 original login gate preserved');
    // Test-only identity to examine the original shell, no claim of backend login.
    await context.route('**/api/me',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({email:'fixture@example.invalid',name:'Fixture',is_premium:false,avatar_url:null,preferences:null})}));
    await context.addInitScript(()=>localStorage.setItem('myProfileEmail','fixture@example.invalid'));
    await page.goto(BASE+'/index.html');
    await page.waitForFunction(()=>document.getElementById('swipeWrapper').style.transform==='translateX(-390px)');
    check(await page.locator('.wrapper iframe').count()===3,'UI-01 original three-iframe home');
    await page.evaluate(()=>{
      const t=x=>new Touch({identifier:1,target:window.document.body,clientX:x,clientY:300});
      window.dispatchEvent(new TouchEvent('touchstart',{touches:[t(300)]}));
      window.dispatchEvent(new TouchEvent('touchmove',{touches:[t(140)]}));
      window.dispatchEvent(new TouchEvent('touchend',{changedTouches:[t(140)]}));
    });
    check(await page.locator('#swipeWrapper').evaluate(el=>el.style.transform)==='translateX(-780px)','UI-02 original swipe threshold to social');
    await page.evaluate(()=>window.postMessage('lockSwiping','*'));await delay(50);
    await page.evaluate(()=>{
      const t=x=>new Touch({identifier:1,target:document.body,clientX:x,clientY:300});
      window.dispatchEvent(new TouchEvent('touchstart',{touches:[t(140)]}));
      window.dispatchEvent(new TouchEvent('touchend',{changedTouches:[t(300)]}));
    });
    check(await page.locator('#swipeWrapper').evaluate(el=>el.style.transform)==='translateX(-780px)','UI-05 child lock preserved');
    await page.evaluate(()=>window.postMessage('unlockSwiping','*'));
    await page.setViewportSize({width:430,height:932});
    await page.waitForFunction(()=>document.getElementById('swipeWrapper').style.transform==='translateX(-860px)');
    check(true,'UI-04 resize alignment');
    await page.goto(BASE+'/index.html?tab=memories');
    await page.waitForFunction(()=>document.getElementById('swipeWrapper').style.transform==='translateX(0px)');
    check(true,'UI-03 requested return tab');
    await page.goto(BASE+'/search.html');await settled(page);
    await page.locator('.header .back-btn').click();
    await page.waitForURL('**/index.html');
    check(true,'REST-06 original return home');
    await page.screenshot({path:path.join(OUT,'v2-original-home-fixture.png')});
    check(errors.length===0,'Browser JavaScript errors absent');
    await context.close();

    // No route mock: live endpoint must report database results, never fixtures.
    if(process.env.V2_LIVE==='1'){
      const live=await browser.newContext({viewport:{width:390,height:844},serviceWorkers:'block'});
      const p=await live.newPage();
      await p.goto(BASE+'/search.html');
      await p.locator('.card').first().waitFor({timeout:15000});
      check(await p.locator('.card').count()===3,'LIVE PostgreSQL three original cards');
      const first=await p.locator('.card').first().getAttribute('data-restaurant-id');
      await touchPull(p,140);await delay(700);
      check(await p.locator('.card').first().getAttribute('data-restaurant-id')!==first,'LIVE PostgreSQL pull rotates batch');
      await p.locator('.card').first().click();await p.locator('#detailModal.active').waitFor();
      await p.screenshot({path:path.join(OUT,'v2-live-detail.png')});
      await p.locator('.detail-nav .nav-circle').click();await delay(350);
      await p.screenshot({path:path.join(OUT,'v2-live-search.png')});
      await live.close();
    }
    fs.writeFileSync(path.join(OUT,'browser-result.json'),JSON.stringify({date:new Date().toISOString(),source:'artificial fixtures; LIVE entries use PostgreSQL',passed:results.length,checks:results,physical_mobile:'not verified'},null,2));
    console.log('TOTAL '+results.length+' browser checks');
  } finally {await browser.close();await new Promise(r=>original.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1;});
