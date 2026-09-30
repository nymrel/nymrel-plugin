// Synthetic MCP host exercise. This is browser proof, not ChatGPT activation proof.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { chromium } from 'playwright';

const html = await readFile(new URL('../hosted-mcp/api/assets/audit-widget.html', import.meta.url), 'utf8');
const payload = {requested_url:'https://example.com',report:{score:72,grade:'C',ai_discoverability_status:'PARTIAL',schema_detected:['WebSite'],recommendations:['Declare one canonical URL.','<img src=x onerror="window.injected=true">'],full_report_url:'https://nymrel.com/site-audit'}};
const browser = await chromium.launch(process.env.BROWSER_CHANNEL ? {channel:process.env.BROWSER_CHANNEL} : {});
try {
  const page = await browser.newPage({viewport:{width:960,height:950}});
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.setContent('<iframe title="Nymrel audit" style="width:100%;height:900px;border:0"></iframe>');
  await page.evaluate(({html,payload}) => {
    window.appInitialized = false;
    const frame = document.querySelector('iframe');
    window.addEventListener('message', event => {
      if (event.source !== frame.contentWindow) return;
      const message = event.data;
      if (message.method === 'ui/initialize') frame.contentWindow.postMessage({jsonrpc:'2.0',id:message.id,result:{protocolVersion:'2026-01-26',hostCapabilities:{},hostContext:{theme:'light',styles:{variables:{'--color-text-primary':'#253c33'}}}}}, '*');
      if (message.method === 'ui/notifications/initialized') {
        window.appInitialized = true;
        frame.contentWindow.postMessage({jsonrpc:'2.0',method:'ui/notifications/tool-result',params:{structuredContent:payload}}, '*');
      }
    });
    frame.srcdoc = html;
  }, {html,payload});
  await page.waitForFunction(() => window.appInitialized);
  const frame = page.frameLocator('iframe');
  await frame.locator('#report').waitFor({state:'visible'});
  assert.equal(await frame.locator('#score').textContent(), '72');
  assert.match(await frame.locator('#identity').textContent(), /cannot verify which page/);
  assert.equal(await frame.locator('#recommendations img').count(), 0);
  assert.equal(await frame.locator('#recommendations li').count(), 2);
  assert.ok(!(await frame.locator('body').innerText()).includes('HTTP 0'));
  await frame.locator('summary').click();
  assert.ok((await frame.locator('#evidence').textContent()).includes('schema_detected'));
  if (process.env.AUDIT_UI_SCREENSHOT) await page.screenshot({path:process.env.AUDIT_UI_SCREENSHOT,fullPage:true});
  await page.setViewportSize({width:390,height:844});
  const child = page.frames()[1];
  assert.ok(await child.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await child.evaluate(() => window.postMessage({jsonrpc:'2.0',method:'ui/notifications/tool-result',params:{isError:true}}, '*'));
  assert.equal(await frame.locator('#report').isVisible(), true, 'ignore messages from a non-host source');
  const send = params => page.evaluate(params => document.querySelector('iframe').contentWindow.postMessage({jsonrpc:'2.0',method:'ui/notifications/tool-result',params}, '*'), params);
  await send({structuredContent:{report:{score:0}}});
  await frame.locator('#report').waitFor({state:'hidden'});
  assert.match(await frame.locator('#state').textContent(), /complete audit result/);
  await send({structuredContent:{...payload,report:{...payload.report,recommendations:[],schema_detected:[]}}});
  await frame.locator('#empty').waitFor({state:'visible'});
  assert.match(await frame.locator('#empty').textContent(), /does not confirm/);
  await send({structuredContent:{...payload,requested_url:'https://requested.example',report:{...payload.report,url:'https://returned.example'}}});
  await frame.locator('#identity').filter({hasText:'https://returned.example'}).waitFor();
  assert.match(await frame.locator('#target').textContent(), /supplied by the caller: https:\/\/requested.example/);
  assert.match(await frame.locator('#identity').textContent(), /does not independently verify page identity/);
  await send({isError:true});
  await frame.locator('#report').waitFor({state:'hidden'});
  assert.deepEqual(errors, []);
  console.log('PASS: initialize, tool result, evidence, mobile, untrusted text/source, empty/error states');
} finally {await browser.close();}
