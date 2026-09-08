const {chromium} = require('playwright');
const assert = require('node:assert/strict');
(async () => {
  const browser = await chromium.launch({headless:true, channel:'msedge'});
  const context = await browser.newContext({viewport:{width:1280,height:900}});
  const page = await context.newPage();
  try {
    const response = await context.request.get('http://127.0.0.1:8000/api/v1/restaurants?page_size=12');
    assert.equal(response.status(),200);
    const data = await response.json();
    assert.ok(data.items.length>0);
    await page.goto('http://127.0.0.1:8000/');
    await page.locator('.card').first().waitFor();
    assert.equal(await page.locator('.card').count(),data.items.length);
    await page.locator('.card').first().click();
    await page.locator('#detail-title').filter({hasText:data.items[0].name}).waitFor();
    assert.equal(new URL(page.url()).searchParams.get('restaurant'), data.items[0].id);
    await page.locator('#close-detail').click();
    await page.screenshot({path:'test-results/live-desktop.png'});
    console.log('PASS live PostgreSQL -> API -> restaurant list -> actual ID detail -> close');
  } finally { await browser.close(); }
})().catch(e=>{console.error(e);process.exitCode=1});
