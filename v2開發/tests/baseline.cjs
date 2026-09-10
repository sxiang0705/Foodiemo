/* Capture original UI baselines; API responses are explicitly artificial. */
const {chromium}=require('playwright');
const fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const root=path.resolve(__dirname,'..'),source=path.resolve(root,'../前端原始程式碼/frontend');
const out=path.join(root,'test-results/baseline');fs.mkdirSync(out,{recursive:true});
(async()=>{
 const mime={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.jpg':'image/jpeg','.png':'image/png','.ico':'image/x-icon','.json':'application/json'};
 const server=http.createServer((req,res)=>{
  const name=decodeURIComponent(new URL(req.url,'http://localhost').pathname).slice(1)||'index.html';
  if(name.includes('/')||name.includes('..')||!mime[path.extname(name)])return res.writeHead(404).end();
  if(['env.js','google-auth-config.js'].includes(name))return res.writeHead(200,{'Content-Type':'text/javascript'}).end('');
  const p=path.join(source,name);if(!fs.existsSync(p))return res.writeHead(404).end();
  res.writeHead(200,{'Content-Type':mime[path.extname(name)]});fs.createReadStream(p).pipe(res);
 });
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const browser=await chromium.launch({headless:true,channel:'msedge'}),report=[];
 try{
  for(const name of fs.readdirSync(source).filter(x=>x.endsWith('.html')&&x!=='search.html')){
   const context=await browser.newContext({viewport:{width:390,height:844},serviceWorkers:'block'});
   await context.addInitScript(({loggedIn})=>{
    Math.random=()=>0.42;if(loggedIn)localStorage.setItem('myProfileEmail','fixture@example.invalid');
   },{loggedIn:!['login.html','signup.html','forgot-password.html','otp_verify.html','reset_password.html','onboarding.html'].includes(name)});
   await context.route('**/*',route=>{
    const url=new URL(route.request().url());
    if(url.pathname.startsWith('/api/'))return route.fulfill({contentType:'application/json',body:JSON.stringify(url.pathname.includes('get_memories')?[]:{is_vip:false}),
      headers:{'Access-Control-Allow-Origin':route.request().headers().origin||'*','Access-Control-Allow-Credentials':'true'}});
    if(url.hostname!=='127.0.0.1')return route.abort();
    return route.continue();
   });
   const pages=[];
   for(const [label,base] of [['original','http://127.0.0.1:'+server.address().port],['v2','http://127.0.0.1:8002']]){
    const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.goto(base+'/'+name);await page.waitForTimeout(350);
    await page.screenshot({path:path.join(out,label+'-'+name+'.png')});
    pages.push({label,url:new URL(page.url()).pathname,errors});
    await page.close();
   }
   report.push({page:name,source:'artificial fixtures; remote assets blocked',captures:pages});
   await context.close();
  }
  fs.writeFileSync(path.join(out,'manifest.json'),JSON.stringify(report,null,2));
  console.log('Captured '+report.length+' original/v2 page pairs; these are UI baseline records, not backend verification.');
 }finally{await browser.close();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1;});

