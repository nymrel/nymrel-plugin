import assert from "node:assert/strict";
import { createServer } from "node:http";
import { mkdir, readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { chromium } from "playwright";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const asset = await readFile(path.join(root, "hosted-mcp", "api", "assets", "workbench.html"), "utf8");
const screenshotDirectory = process.env.NYMREL_UI_SCREENSHOT_DIR;
if (screenshotDirectory) await mkdir(screenshotDirectory, {recursive:true});
// Contract from nymrel/nymrel src/app/api/v1/tools/_lib/contracts.ts at
// upstream main 814303a9ef52501e477a5ee10517b87debf4cf75.
const acceptedClipPlatforms = new Set(["tiktok", "instagram_reels", "youtube_shorts", "x"]);
for (const notice of [
  "@modelcontextprotocol/ext-apps 2.0.3 (MIT)",
  "@modelcontextprotocol/client 2.4.0 (Apache-2.0)",
  "@modelcontextprotocol/core 2.4.0 (Apache-2.0)",
  "zod 4.6.7 (MIT)",
  "Permission is hereby granted, free of charge",
  "The above copyright notice and this permission notice shall be included",
  "Apache License",
]) assert.ok(asset.includes(notice), `generated asset must retain bundled license text: ${notice}`);
const hostPage = `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Synthetic host</title></head>
<body style="margin:0"><iframe id="workbench-frame" title="Nymrel tool workbench" src="/workbench.html" style="border:0;width:100vw;height:100vh"></iframe>
<script>
(() => {
  const mode = new URL(location.href).searchParams.get('mode') || 'normal';
  const frame = document.getElementById('workbench-frame');
  const state = window.__testHost = {
    calls: [], updates: [], displayRequests: 0, connected: false, contextQueue: [], initializeAttempts:0, dropTools:mode === 'tool-timeout', dropContext:false,
    queues: Object.create(null), pendingTools: Object.create(null), pendingContexts: [],
    opener: {version:'1.0', default_tool:'website', tools:[
      {id:'website',name:'nymrel_audit_website',title:'Website audit',description:'Measure one public page.'},
      {id:'domains',name:'nymrel_find_domain',title:'Domain ideas',description:'Explore available names.'},
      {id:'golf',name:'nymrel_golf_bag_gap',title:'Golf bag gaps',description:'Compare carries.'},
      {id:'clip',name:'nymrel_social_clip_score',title:'Social clip signals',description:'Measure hook signals.'}
    ]},
    capabilities: mode === 'disabled' ? {} : mode === 'no-context' ? {serverTools:{}} : {serverTools:{},updateModelContext:{text:{}}},
    context: {
      theme: 'light', displayMode:'inline', availableDisplayModes:mode === 'inline' ? ['inline'] : ['inline','fullscreen'],
      'openai/deepLink': mode === 'deep' ? {url:'/golf'} : undefined,
      styles:{variables:{'--color-background-primary':'#fffefa','--color-text-primary':'#26362f'}}
    },
    respond(name, result, delay=0) {
      const queue = this.queues[name] || (this.queues[name] = []);
      queue.push({result,delay});
    },
    hold(name, result) {
      const queue = this.queues[name] || (this.queues[name] = []);
      queue.push({result,held:true});
    },
    releaseTool(name) {
      const send = this.pendingTools[name]?.shift();
      if (!send) throw new Error('No held tool response for ' + name);
      send();
    },
    reject(name, error) {
      const queue = this.queues[name] || (this.queues[name] = []);
      queue.push({error});
    },
    respondContext(error=null, delay=0) { this.contextQueue.push({error,delay}); },
    holdContext() { this.contextQueue.push({held:true}); },
    releaseContext() {
      const send = this.pendingContexts.shift();
      if (!send) throw new Error('No held conversation response');
      send();
    },
    notify(method, params) { frame.contentWindow.postMessage({jsonrpc:'2.0',method,params}, '*'); },
    changeContext(patch) {
      this.context = {...this.context,...patch};
      this.notify('ui/notifications/host-context-changed', patch);
    }
  };
  const defaults = {
    nymrel_audit_website:{score:84,grade:'B',ai_discoverability_status:'Some signals found',recommendations:[],schema_detected:[],full_report_url:'https://example.test/report'},
    nymrel_find_domain:{suggestions:[{domain:'sample.example',available:false,availability_checked:false,brandability_score:72,brandability_factors:{label_length:6,contains_digit:false,contains_hyphen:false,contains_vowel:true}}]},
    nymrel_golf_bag_gap:{average_gap_yards:13,problem_gaps:['A < 10 yard gap'],recommendations:['Check the 5 iron carry.']},
    nymrel_social_clip_score:{target_platform:'tiktok',hook_score:77,hook_strength:'Strong',signals:{opening_word_count:7,opens_with_hook_pattern:true,addresses_viewer:true,has_curiosity_signal:false,opening_contains_number:false,total_word_count:21,platform_word_range:[20,40],total_word_count_in_platform_range:true},suggested_edits:['Try a shorter opening.']}
  };
  state.defaults = defaults;
  window.addEventListener('message', (event) => {
    if (event.source !== frame.contentWindow || event.data?.jsonrpc !== '2.0') return;
    const message = event.data;
    if (!message.method) return;
    const respond = (result) => frame.contentWindow.postMessage({jsonrpc:'2.0',id:message.id,result}, '*');
    if (message.method === 'ui/initialize') {
      state.initializeAttempts += 1;
      if (mode === 'timeout' || (mode === 'reconnect' && state.initializeAttempts === 1)) return;
      state.connected = true;
      respond({protocolVersion:'2025-11-25',hostInfo:{name:'synthetic-host',version:'1'},hostCapabilities:state.capabilities,hostContext:state.context});
    } else if (message.method === 'ui/notifications/initialized') {
      setTimeout(() => state.notify('ui/notifications/tool-result', {structuredContent:state.opener,content:[{type:'text',text:'Tools ready.'}]}), 0);
    } else if (message.method === 'ui/request-display-mode') {
      state.displayRequests += 1;
      if (mode === 'fullscreen-denied') {
        frame.contentWindow.postMessage({jsonrpc:'2.0',id:message.id,error:{code:-32603,message:'Synthetic fullscreen rejection'}}, '*');
        return;
      }
      state.context.displayMode = message.params.mode;
      respond({mode:message.params.mode});
    } else if (message.method === 'ui/update-model-context') {
      state.updates.push(message.params);
      if (state.dropContext) return;
      const fixture = state.contextQueue.shift() || {};
      const send = () => fixture.error
        ? frame.contentWindow.postMessage({jsonrpc:'2.0',id:message.id,error:fixture.error}, '*')
        : respond({});
      if (fixture.held) state.pendingContexts.push(send);
      else setTimeout(send, fixture.delay || 0);
    } else if (message.method === 'tools/call') {
      const name = message.params?.name;
      const queue = state.queues[name] || [];
      const next = queue.shift();
      const data = name === 'nymrel_social_clip_score' ? {...defaults[name], target_platform:message.params.arguments.target_platform} : defaults[name];
      const fixture = next || {result:{structuredContent:data || {},content:[{type:'text',text:'ok'}]}};
      state.calls.push({name,arguments:message.params?.arguments || {}});
      if (state.dropTools) return;
      const send = () => fixture.error
        ? frame.contentWindow.postMessage({jsonrpc:'2.0',id:message.id,error:fixture.error}, '*')
        : respond(fixture.result);
      if (fixture.held) (state.pendingTools[name] || (state.pendingTools[name] = [])).push(send);
      else setTimeout(send, fixture.delay || 0);
    } else if (message.method === 'ui/notifications/size-changed' || message.method === 'notifications/message') {
      // Notifications require no response.
    }
  });
})();
</script></body></html>`;

const server = createServer((request, response) => {
  if (request.url === "/workbench.html") {
    response.writeHead(200, { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" });
    response.end(asset);
  } else if (request.url?.startsWith("/?mode=") || request.url === "/") {
    response.writeHead(200, { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" });
    response.end(hostPage);
  } else if (request.url === "/favicon.ico") {
    response.writeHead(204); response.end();
  } else {
    response.writeHead(404); response.end();
  }
});
await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const { port } = server.address();
const base = `http://127.0.0.1:${port}`;
let browser;

function toolTab(frame, id) { return frame.locator(`#tab-${id}`); }
async function chooseTool(frame, id) { await toolTab(frame, id).click(); }
async function getHost(page, expression) { return page.evaluate(expression); }
async function releaseTool(page, name) {
  await page.waitForFunction((tool) => window.__testHost.pendingTools[tool]?.length > 0, name);
  await page.evaluate((tool) => window.__testHost.releaseTool(tool), name);
}
async function releaseContext(page) {
  await page.waitForFunction(() => window.__testHost.pendingContexts.length > 0);
  await page.evaluate(() => window.__testHost.releaseContext());
}

try {
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1180, height: 900 } });
  page.setDefaultTimeout(8000);
  page.on("pageerror", (error) => process.stderr.write(`pageerror: ${error.stack || error.message}\n`));
  page.on("console", (message) => { if (message.type() === "error") process.stderr.write(`console: ${message.text()}\n`); });
  await page.goto(base);
  const frame = page.frameLocator("#workbench-frame");
  await frame.locator("#workbench").waitFor({ state: "visible", timeout: 10000 });
  await frame.locator("#host-status").waitFor({ state: "hidden" });
  assert.equal(await frame.locator("#tab-website").getAttribute("aria-selected"), "true", "opener result is consumed without changing the initial view");
  assert.equal(await getHost(page, "window.__testHost.calls.length"), 0, "launch must not call a public tool");
  assert.equal(await getHost(page, "window.__testHost.displayRequests"), 1, "fullscreen is requested once when advertised");

  const hostile = "<img src=x onerror=window.__injected=1> measured recommendation";
  const beforeWebsite = await getHost(page, "window.__testHost.calls.length");
  await frame.locator("#website-url").fill("https://guest:secret@example.test");
  await frame.locator("#form-website button[type=submit]").click();
  await frame.getByText("Use a public URL without embedded credentials.", { exact: true }).waitFor();
  assert.equal(await frame.locator("#website-url").evaluate((element) => element === document.activeElement), true);
  assert.equal(await getHost(page, "window.__testHost.calls.length"), beforeWebsite, "credential-bearing URLs are rejected locally");
  await page.evaluate(() => window.__testHost.hold("nymrel_audit_website", {structuredContent:{score:84,grade:"B",ai_discoverability_status:"Readable",recommendations:["<img src=x onerror=window.__injected=1> measured recommendation"],schema_detected:["Product"],full_report_url:"https://example.test/report"},content:[{type:"text",text:"Website audit result"}]}));
  await frame.locator("#website-url").fill("https://example.test");
  await frame.locator("#form-website button[type=submit]").click();
  await frame.getByText("Checking the public page…").waitFor();
  assert.equal(await frame.locator("#form-website button[type=submit]").isDisabled(), true);
  assert.equal(await frame.locator("#form-website").getAttribute("aria-busy"), "true");
  await releaseTool(page, "nymrel_audit_website");
  await frame.getByText("84 / 100").waitFor();
  assert.equal(await getHost(page, "window.__testHost.calls.at(-1).name"), "nymrel_audit_website");
  assert.deepEqual(await getHost(page, "window.__testHost.calls.at(-1).arguments"), {url:"https://example.test"});
  assert.equal(await frame.locator("img").count(), 0, "untrusted result text is rendered as text");
  assert.equal(await frame.getByText(hostile, {exact:true}).count(), 1);
  assert.equal(await page.evaluate(() => window.__injected || false), false);
  assert.equal(await getHost(page, "window.__testHost.updates.length"), 0, "model context is not updated automatically");
  await frame.getByRole("button", {name:"Use result in conversation"}).click();
  await page.waitForFunction(() => window.__testHost.updates.length === 1);
  assert.match((await getHost(page, "window.__testHost.updates[0].content[0].text")), /score 84\/100/);

  await chooseTool(frame, "domains");
  await frame.locator("#domain-idea").fill("mobile dog grooming");
  await frame.locator("#domain-tlds").fill("com");
  const beforeBadTld = await getHost(page, "window.__testHost.calls.length");
  await frame.locator("#form-domains button[type=submit]").click();
  await frame.getByText("Enter domain endings like .com or .io, separated by commas.").waitFor();
  assert.equal(await frame.locator("#domain-tlds").evaluate((element) => element === document.activeElement), true);
  assert.equal(await getHost(page, "window.__testHost.calls.length"), beforeBadTld, "invalid TLD is rejected locally");
  await frame.locator("#domain-tlds").fill(".com, .IO");
  await frame.locator("#form-domains button[type=submit]").click();
  await frame.getByText("Availability not checked", { exact: false }).waitFor();
  assert.deepEqual(await getHost(page, "window.__testHost.calls.at(-1).arguments"), {keyword_or_concept:"mobile dog grooming",tlds:[".com",".io"]});

  await chooseTool(frame, "golf");
  let golfRows = frame.locator(".club-row");
  await golfRows.nth(0).locator(".club-name").fill("7 iron");
  await golfRows.nth(0).locator(".club-carry").fill("165");
  await golfRows.nth(0).locator(".club-loft").fill("30.5");
  await frame.locator("#add-club").click();
  golfRows = frame.locator(".club-row");
  await golfRows.nth(1).locator(".club-name").fill("5 iron");
  await golfRows.nth(1).locator(".club-carry").fill("185");
  await golfRows.nth(1).locator(".remove-club").click();
  assert.equal(await frame.locator(".club-row").count(), 1, "club rows can be removed");
  await frame.locator("#add-club").click();
  golfRows = frame.locator(".club-row");
  await golfRows.nth(1).locator(".club-name").fill("5 iron");
  await golfRows.nth(1).locator(".club-carry").fill("185");
  await frame.locator("#form-golf button[type=submit]").click();
  await frame.getByText("Average gap").waitFor();
  assert.deepEqual(await getHost(page, "window.__testHost.calls.at(-1).arguments"), {clubs:[{name:"7 iron",carry_distance_yards:165,loft_degrees:30.5},{name:"5 iron",carry_distance_yards:185}]});

  await chooseTool(frame, "clip");
  const clipPlatformValues = await frame.locator("#clip-platform option").evaluateAll((options) => options.map((option) => option.value));
  const defaultPlatformValues = await frame.locator("#default-platform option").evaluateAll((options) => options.map((option) => option.value));
  assert.deepEqual(clipPlatformValues, ["tiktok", "instagram_reels", "youtube_shorts"], "short-form choices use the upstream API identifiers");
  assert.deepEqual(defaultPlatformValues, clipPlatformValues, "clip and preference choices stay in sync");
  assert.equal(new Set(clipPlatformValues).size, clipPlatformValues.length, "clip platform values are unique");
  assert.ok(clipPlatformValues.every((platform) => acceptedClipPlatforms.has(platform)), "every displayed platform is accepted by the current public API contract");
  await frame.locator("#clip-transcript").fill("Stop doing this in Python right now.");
  await frame.locator("#clip-platform").selectOption("youtube_shorts");
  await page.evaluate(() => window.__testHost.hold("nymrel_social_clip_score", {structuredContent:{target_platform:"youtube_shorts",hook_score:77,hook_strength:"Strong",signals:{opening_word_count:7,opens_with_hook_pattern:true,addresses_viewer:true,has_curiosity_signal:false,opening_contains_number:false,total_word_count:21,platform_word_range:[20,40],total_word_count_in_platform_range:true},suggested_edits:["Try a shorter opening."]},content:[{type:"text",text:"clip result"}]}));
  await frame.locator("#form-clip button[type=submit]").click();
  await frame.getByText("Measuring the opening…").waitFor();
  assert.equal(await frame.locator("#form-clip button[type=submit]").isDisabled(), true, "an in-flight tool call cannot be duplicated");
  await chooseTool(frame, "golf");
  await frame.getByText("Average gap").waitFor();
  await releaseTool(page, "nymrel_social_clip_score");
  await page.waitForFunction(() => !document.querySelector("#workbench-frame").contentDocument.querySelector("#form-clip button[type=submit]").disabled);
  assert.equal(await frame.locator("#tab-golf").getAttribute("aria-selected"), "true", "a late response does not steal the active tool view");
  await chooseTool(frame, "clip");
  await frame.getByText("77 / 100").waitFor();
  assert.deepEqual(await getHost(page, "window.__testHost.calls.at(-1).arguments"), {transcript_text:"Stop doing this in Python right now.",target_platform:"youtube_shorts"});
  const clipSuccess = {structuredContent:{target_platform:"tiktok",hook_score:77,hook_strength:"Strong",signals:{opening_word_count:7,opens_with_hook_pattern:true,addresses_viewer:true,has_curiosity_signal:false,opening_contains_number:false,total_word_count:21,platform_word_range:[20,40],total_word_count_in_platform_range:true},suggested_edits:["Try a shorter opening."]},content:[{type:"text",text:"clip result"}]};
  for (const platform of clipPlatformValues) {
    await frame.locator("#clip-platform").selectOption(platform);
    const callsBefore = await getHost(page, "window.__testHost.calls.length");
    await page.evaluate((result) => window.__testHost.hold("nymrel_social_clip_score", result), {...clipSuccess, structuredContent:{...clipSuccess.structuredContent,target_platform:platform}});
    await frame.locator("#form-clip button[type=submit]").click();
    await frame.getByText("Measuring the opening…").waitFor();
    assert.equal(await frame.locator("#form-clip button[type=submit]").isDisabled(), true);
    assert.equal(await frame.locator("#form-clip").getAttribute("aria-busy"), "true");
    await frame.locator("#form-clip").evaluate((element) => element.dispatchEvent(new Event("submit", {bubbles:true,cancelable:true})));
    await releaseTool(page, "nymrel_social_clip_score");
    await frame.locator("#status-clip").getByText("Result ready.", { exact: false }).waitFor();
    await frame.getByText("77 / 100").waitFor();
    assert.equal(await getHost(page, "window.__testHost.calls.length"), callsBefore + 1, "a pending clip call rejects duplicate submission");
    assert.deepEqual(await getHost(page, "window.__testHost.calls.at(-1).arguments"), {
      transcript_text:"Stop doing this in Python right now.", target_platform:platform,
    }, `${platform} must be sent exactly as accepted by the public API`);
  }

  await page.evaluate(() => window.__testHost.respond("nymrel_find_domain", {isError:true,structuredContent:{status:"error",error:{code:"UPSTREAM_NOT_DEPLOYED",message:"Nymrel could not check this idea right now."}},content:[{type:"text",text:"Nymrel could not check this idea right now."}]}));
  await chooseTool(frame, "domains");
  await frame.locator("#form-domains button[type=submit]").click();
  await frame.locator("#status-domains").getByText("Nymrel could not check this idea right now.", { exact: false }).waitFor();
  assert.equal(await frame.locator("#form-domains button[type=submit]").isDisabled(), false, "failed calls can be retried");
  await page.evaluate(() => window.__testHost.respond("nymrel_find_domain", {structuredContent:{suggestions:[{domain:"retried.example",available:true,availability_checked:true,brandability_score:80,brandability_factors:{label_length:7,contains_digit:false,contains_hyphen:false,contains_vowel:true}}]},content:[{type:"text",text:"retry ok"}]}));
  await frame.locator("#form-domains button[type=submit]").click();
  await frame.getByText("Available when checked").waitFor();

  await chooseTool(frame, "clip");
  await frame.locator("#clip-transcript").fill("Draft text stays while context changes.");
  await page.evaluate(() => window.__testHost.changeContext({theme:"dark", "openai/deepLink":{url:"/golf"}}));
  await frame.locator('#tab-golf[aria-selected="true"]').waitFor({ state: "visible" });
  assert.equal(await frame.locator("#tab-golf").getAttribute("aria-selected"), "true", "supported deep link selects a tab");
  await chooseTool(frame, "clip");
  assert.equal(await frame.locator("#clip-transcript").inputValue(), "Draft text stays while context changes.", "host context changes preserve unsaved fields");
  assert.equal(await frame.locator("html").evaluate((el) => el.style.colorScheme), "dark", "host theme changes are applied");
  await frame.locator("#settings summary").click();
  await frame.locator("#show-evidence").check();
  await frame.locator("#domain-tlds").waitFor({ state: "attached" });
  assert.equal(await frame.locator("pre[data-testid=evidence]").isVisible(), true, "evidence preference applies to prior in-memory result");
  assert.equal(await getHost(page, `localStorage.getItem('nymrel-workbench-preferences-v1') !== null`), true, "only display preferences use localStorage");

  await page.setViewportSize({ width: 360, height: 780 });
  const widths = await frame.locator("body").evaluate((body) => ({ scroll: body.scrollWidth, client: body.clientWidth }));
  assert.ok(widths.scroll <= widths.client + 1, `mobile content overflows horizontally (${JSON.stringify(widths)})`);
  assert.equal(await getHost(page, "window.__testHost.calls.some((call) => call.name === 'nymrel_open_tools')"), false, "the UI never calls its opener again");

  // Recovery is exercised through SDK messages, with synthetic native payloads
  // only. Each tool must retain its successful data and submitted input context.
  const recoveryTools = [
    {id:"website", name:"nymrel_audit_website", field:"#website-url", initial:"https://first.example.test", edited:"https://second.example.test"},
    {id:"domains", name:"nymrel_find_domain", field:"#domain-idea", initial:"first concept", edited:"second concept"},
    {id:"golf", name:"nymrel_golf_bag_gap", field:".club-name", initial:"First iron", edited:"Second iron"},
    {id:"clip", name:"nymrel_social_clip_score", field:"#clip-transcript", initial:"First spoken hook.", edited:"Second spoken hook."},
  ];
  for (const tool of recoveryTools) {
    const recoveryPage = await browser.newPage({viewport:{width:320,height:780}});
    recoveryPage.setDefaultTimeout(8000);
    await recoveryPage.goto(base);
    const recoveryFrame = recoveryPage.frameLocator("#workbench-frame");
    await recoveryFrame.locator("#workbench").waitFor({state:"visible"});
    await chooseTool(recoveryFrame, tool.id);
    const input = recoveryFrame.locator(tool.field).first();
    const submit = recoveryFrame.locator(`#form-${tool.id} button[type=submit]`);
    const status = recoveryFrame.locator(`#status-${tool.id}`);
    await submit.focus();
    await submit.press("Enter");
    assert.equal(await input.evaluate((element) => element === document.activeElement), true, `${tool.id} validation focuses the first invalid field`);
    assert.equal(await input.getAttribute("aria-invalid"), "true");
    assert.match(await input.getAttribute("aria-describedby"), new RegExp(`status-${tool.id}`));
    assert.equal(await getHost(recoveryPage, "window.__testHost.calls.length"), 0);
    await input.fill(tool.initial);
    assert.equal(await input.getAttribute("aria-invalid"), null, "editing clears the field error marker");
    if (tool.id === "golf") await recoveryFrame.locator(".club-carry").fill("165");

    await recoveryPage.evaluate((name) => window.__testHost.respond(name, {structuredContent:{},content:[{type:"text",text:"not a report"}]}), tool.name);
    await submit.click();
    await status.getByText("Nymrel returned an incomplete or invalid result.", {exact:false}).waitFor();
    assert.equal(await status.getAttribute("data-kind"), "error");
    assert.equal(await recoveryFrame.locator("#result").isVisible(), false, "a malformed first response creates no report");
    assert.equal(await recoveryFrame.getByRole("button", {name:/Use .*result in conversation/}).count(), 0);

    await submit.click();
    await status.getByText("Result ready.", {exact:false}).waitFor();
    await recoveryFrame.locator("#settings summary").click();
    await recoveryFrame.locator("#show-evidence").check();
    const evidence = recoveryFrame.locator('pre[data-testid="evidence"]');
    const goodData = await evidence.textContent();
    const goodArgs = await getHost(recoveryPage, "window.__testHost.calls.at(-1).arguments");
    await input.fill(tool.edited);
    const title = recoveryFrame.locator('[data-testid="result-title"]');
    const provenance = recoveryFrame.locator('[data-testid="result-provenance"]');
    await provenance.getByText("Inputs have changed.", {exact:false}).waitFor();
    assert.match(await title.textContent(), /previous successful result/);
    await recoveryFrame.getByRole("button", {name:"Use previous result in conversation"}).click();
    await recoveryPage.waitForFunction(() => window.__testHost.updates.length === 1);
    let summary = await getHost(recoveryPage, "window.__testHost.updates.at(-1).content[0].text");
    assert.match(summary, /^Previous successful result\./);
    assert.ok(summary.includes(tool.initial), "conversation summary carries the result's submitted inputs");
    if (tool.id === "golf") assert.ok(summary.includes(`${goodArgs.clubs[0].carry_distance_yards} yards`));
    if (tool.id === "clip") assert.ok(summary.includes("Target platform: TikTok"));
    assert.ok(!summary.includes(tool.edited), "edited fields cannot be passed off as the old report's inputs");
    await input.fill(tool.initial);

    await recoveryFrame.locator('[data-testid="share-status"]').getByText("The result summary is now in the conversation.").waitFor();
    await recoveryPage.evaluate(() => window.__testHost.holdContext());
    const shareRequestsBefore = await getHost(recoveryPage, "window.__testHost.updates.length");
    await recoveryFrame.getByRole("button", {name:"Use result in conversation"}).click();
    await recoveryFrame.locator('[data-testid="share-status"]').getByText("Adding the result summary", {exact:false}).waitFor();
    await recoveryFrame.locator("#show-evidence").uncheck();
    await recoveryFrame.locator("#show-evidence").check();
    assert.equal(await recoveryFrame.getByRole("button", {name:"Use result in conversation"}).isDisabled(), true, `${tool.id}: display changes must not re-enable an in-flight handoff`);
    await recoveryFrame.getByRole("button", {name:"Use result in conversation"}).evaluate((element) => element.dispatchEvent(new MouseEvent("click", {bubbles:true})));
    await chooseTool(recoveryFrame, tool.id === "website" ? "domains" : "website");
    await chooseTool(recoveryFrame, tool.id);
    assert.equal(await recoveryFrame.getByRole("button", {name:"Use result in conversation"}).isDisabled(), true, `${tool.id}: returning preserves a pending handoff`);
    await releaseContext(recoveryPage);
    await recoveryFrame.locator('[data-testid="share-status"]').getByText("The result summary is now in the conversation.").waitFor();
    assert.equal(await getHost(recoveryPage, "window.__testHost.updates.length"), shareRequestsBefore + 1, "one explicit handoff sends one context update");

    await recoveryPage.evaluate(() => window.__testHost.respondContext({code:-32603,message:"Synthetic conversation failure"}, 50));
    await recoveryFrame.getByRole("button", {name:"Use result in conversation"}).click();
    await recoveryFrame.locator('[data-testid="share-status"]').getByText("This host could not add the result summary.", {exact:false}).waitFor();
    assert.equal(await recoveryFrame.getByRole("button", {name:"Use result in conversation"}).isDisabled(), false, "failed conversation handoff can be retried");
    assert.equal(await evidence.textContent(), goodData, "failed handoff preserves result evidence");
    await chooseTool(recoveryFrame, tool.id === "website" ? "domains" : "website");
    await chooseTool(recoveryFrame, tool.id);
    await recoveryFrame.locator('[data-testid="share-status"]').getByText("This host could not add the result summary.", {exact:false}).waitFor();

    const serviceError = {status:"error",error:{code:"UPSTREAM_UNAVAILABLE",message:"This tool is temporarily unavailable.",retryable:true}};
    const invalidData = JSON.parse(goodData);
    if (tool.id === "website") invalidData.score = "84";
    if (tool.id === "domains") invalidData.suggestions[0].availability_checked = "false";
    if (tool.id === "golf") invalidData.average_gap_yards = "13";
    if (tool.id === "clip") invalidData.target_platform = "x";
    for (const failure of [
      {label:"service",result:{isError:true,structuredContent:serviceError,content:[{type:"text",text:"service error"}]}},
      {label:"error envelope",result:{structuredContent:serviceError,content:[]}},
      {label:"transport",error:{code:-32603,message:"Synthetic transport failure"}},
      {label:"timeout",error:{code:-32001,message:"Synthetic timeout"}},
      {label:"malformed",result:{structuredContent:{},content:[{type:"text",text:"{}"}]}},
      {label:"invalid measurement or platform",result:{structuredContent:invalidData,content:[]}},
      {label:"invalid structured content wins over text",result:{structuredContent:{},content:[{type:"text",text:goodData}]}},
      {label:"structured array",result:{structuredContent:[],content:[{type:"text",text:goodData}]}},
      {label:"unstructured text",result:{content:[{type:"text",text:"The tool says it is ready."}]}},
    ]) {
      await recoveryPage.evaluate(({name,failure}) => {
        if (failure.error) window.__testHost.reject(name, failure.error);
        else window.__testHost.respond(name, failure.result, 80);
      }, {name:tool.name,failure});
      await submit.click();
      await status.locator('text=/You can try again\\./').waitFor();
      assert.equal(await status.getAttribute("data-kind"), "error", `${tool.id}/${failure.label} keeps stable error semantics`);
      assert.ok(!(await status.textContent()).includes("Result ready"));
      assert.equal(await evidence.textContent(), goodData, `${tool.id}/${failure.label} preserves the successful data`);
      assert.match(await title.textContent(), /previous successful result/);
      assert.match(await provenance.textContent(), /latest request failed/);
      assert.equal(await submit.isDisabled(), false);
      assert.equal(await recoveryFrame.locator(`#form-${tool.id}`).getAttribute("aria-busy"), "false");
    }
    if (screenshotDirectory) {
      const fitFrame = async () => {
        const height = await recoveryFrame.locator("body").evaluate((body) => body.scrollHeight);
        await recoveryPage.locator("#workbench-frame").evaluate((element, frameHeight) => { element.style.height = `${frameHeight}px`; }, height);
      };
      await fitFrame();
      await recoveryPage.screenshot({path:path.join(screenshotDirectory, `${tool.id}-recovery-320.png`),fullPage:true});
      await recoveryPage.setViewportSize({width:1180,height:900});
      await fitFrame();
      await recoveryPage.screenshot({path:path.join(screenshotDirectory, `${tool.id}-recovery-desktop.png`),fullPage:true});
      await recoveryPage.setViewportSize({width:320,height:780});
      await recoveryPage.locator("#workbench-frame").evaluate((element) => { element.style.height = "100vh"; });
    }
    // Sharing a previous result is a separate operation and cannot clear the
    // request's error status or silently submit the edited fields.
    const failureMessage = await status.textContent();
    await recoveryFrame.getByRole("button", {name:"Use previous result in conversation"}).click();
    await recoveryFrame.locator('[data-testid="share-status"]').getByText("The result summary is now in the conversation.").waitFor();
    assert.equal(await status.textContent(), failureMessage);
    assert.equal(await recoveryFrame.getByRole("button", {name:"Use previous result in conversation"}).evaluate((element) => element === document.activeElement), true, "sharing preserves keyboard focus");

    const callsBeforeHeldRetry = await getHost(recoveryPage, "window.__testHost.calls.length");
    await recoveryPage.evaluate(({name,data}) => window.__testHost.hold(name, {content:[{type:"text",text:data}]}), {name:tool.name,data:goodData});
    await submit.click();
    await recoveryFrame.getByRole("button", {name:"Use previous result in conversation"}).waitFor();
    await recoveryFrame.getByRole("button", {name:"Use previous result in conversation"}).click();
    assert.equal(await submit.isDisabled(), true, "sharing does not enable an in-flight submit");
    assert.equal(await recoveryFrame.locator(`#form-${tool.id}`).getAttribute("aria-busy"), "true");
    await recoveryFrame.locator(`#form-${tool.id}`).evaluate((element) => element.dispatchEvent(new Event("submit", {bubbles:true,cancelable:true})));
    await input.fill(tool.edited);
    const otherTool = tool.id === "website" ? "domains" : "website";
    await chooseTool(recoveryFrame, otherTool);
    await releaseTool(recoveryPage, tool.name);
    await recoveryPage.waitForFunction((id) => !document.querySelector("#workbench-frame").contentDocument.querySelector(`#form-${id} button[type=submit]`).disabled, tool.id);
    assert.equal(await recoveryFrame.locator(`#tab-${otherTool}`).getAttribute("aria-selected"), "true", `${tool.id}: a late response must not navigate away from the user's chosen tool`);
    await chooseTool(recoveryFrame, tool.id);
    await status.getByText("Result ready for the submitted inputs.", {exact:false}).waitFor();
    assert.equal(await getHost(recoveryPage, "window.__testHost.calls.length"), callsBeforeHeldRetry + 1, `${tool.id}: a pending retry rejects duplicate submission`);
    assert.match(await title.textContent(), /previous successful result/, "input changes during a request remain explicit after success");
    await recoveryFrame.getByText("Inputs used for this result", {exact:true}).click();
    const shownInputs = await recoveryFrame.locator(".result-inputs pre").textContent();
    assert.ok(shownInputs.includes(tool.initial), "submitted input values stay visible after a later edit");
    assert.ok(!shownInputs.includes(tool.edited));
    assert.equal(await evidence.textContent(), goodData);
    const narrowBounds = await recoveryFrame.locator("body").evaluate((body) => ({scroll:body.scrollWidth,client:body.clientWidth}));
    assert.ok(narrowBounds.scroll <= narrowBounds.client + 1, `${tool.id} result/input evidence overflows at 320px: ${JSON.stringify(narrowBounds)}`);
    if (tool.id === "golf") assert.ok(await input.evaluate((element) => element.getBoundingClientRect().width) >= 150, "golf club name stays readable at 320px");
    const tapTargets = await recoveryFrame.locator("button:visible,summary:visible").evaluateAll((elements) => elements.map((element) => element.getBoundingClientRect().height));
    assert.ok(tapTargets.every((height) => height >= 44), `${tool.id} has a tap target smaller than 44px`);
    await submit.click();
    await status.getByText("Result ready.", {exact:false}).waitFor();
    assert.ok(!(await title.textContent()).includes("previous successful result"), "a successful retry replaces the previous result and its provenance");
    assert.match(await provenance.textContent(), /current inputs/);
    assert.ok((await recoveryFrame.locator(".result-inputs pre").textContent()).includes(tool.edited));
    const preferences = await getHost(recoveryPage, "JSON.parse(localStorage.getItem('nymrel-workbench-preferences-v1'))");
    assert.deepEqual(Object.keys(preferences).sort(), ["defaultTool","platform","showEvidence"], "submitted inputs and results are never persisted");
    await recoveryFrame.locator("#tab-website").focus();
    await recoveryFrame.locator("#tab-website").press("End");
    assert.equal(await recoveryFrame.locator("#tab-clip").evaluate((element) => element === document.activeElement), true);
    assert.equal(await recoveryFrame.locator("#tab-clip").getAttribute("aria-selected"), "true");
    await recoveryPage.close();
  }

  const deepPage = await browser.newPage();
  await deepPage.goto(`${base}/?mode=deep`);
  const deepFrame = deepPage.frameLocator("#workbench-frame");
  await deepFrame.locator("#workbench").waitFor({ state: "visible", timeout: 10000 });
  assert.equal(await deepFrame.locator("#tab-golf").getAttribute("aria-selected"), "true", "launch deep link selects the relevant tool");

  const disabledPage = await browser.newPage();
  await disabledPage.goto(`${base}/?mode=disabled`);
  const disabledFrame = disabledPage.frameLocator("#workbench-frame");
  await disabledFrame.locator("#workbench").waitFor({ state: "visible", timeout: 10000 });
  assert.equal(await disabledFrame.locator("#form-website button[type=submit]").isDisabled(), true, "missing serverTools disables tool calls");
  assert.equal(await disabledFrame.locator("#result button").count(), 0);

  for (const mode of ["inline", "fullscreen-denied", "no-context"]) {
    const capabilityPage = await browser.newPage({viewport:{width:320,height:780}});
    await capabilityPage.goto(`${base}/?mode=${mode}`);
    const capabilityFrame = capabilityPage.frameLocator("#workbench-frame");
    await capabilityFrame.locator("#workbench").waitFor({state:"visible"});
    await capabilityFrame.locator("#website-url").fill("https://example.test");
    await capabilityFrame.locator("#form-website button[type=submit]").click();
    await capabilityFrame.locator("#status-website").getByText("Result ready.", {exact:false}).waitFor();
    assert.equal(await getHost(capabilityPage, "window.__testHost.displayRequests"), mode === "inline" ? 0 : 1);
    assert.equal(await capabilityFrame.getByRole("button", {name:"Use result in conversation"}).isDisabled(), mode === "no-context");
    await capabilityPage.close();
  }

  const storagePage = await browser.newPage();
  await storagePage.addInitScript(() => { Storage.prototype.setItem = () => { throw new DOMException("Synthetic unavailable storage", "SecurityError"); }; });
  await storagePage.goto(base);
  const storageFrame = storagePage.frameLocator("#workbench-frame");
  await storageFrame.locator("#workbench").waitFor({state:"visible"});
  await storageFrame.locator("#form-website button[type=submit]").click();
  const invalidStatus = await storageFrame.locator("#status-website").textContent();
  await storageFrame.locator("#settings summary").click();
  await storageFrame.locator("#show-evidence").check();
  assert.equal(await storageFrame.locator("#status-website").textContent(), invalidStatus, "a storage failure must not overwrite request/validation feedback");
  await storageFrame.locator("#preference-status").getByText("Browser storage is unavailable", {exact:false}).waitFor();
  await storageFrame.locator("#website-url").fill("https://example.test");
  await storageFrame.locator("#form-website button[type=submit]").click();
  await storageFrame.locator("#status-website").getByText("Result ready.", {exact:false}).waitFor();
  assert.equal(await storageFrame.locator('pre[data-testid="evidence"]').isVisible(), true, "preferences still work in memory without storage");
  await storagePage.close();

  const emptyPage = await browser.newPage();
  await emptyPage.goto(base);
  const emptyFrame = emptyPage.frameLocator("#workbench-frame");
  await emptyFrame.locator("#workbench").waitFor({state:"visible"});
  await chooseTool(emptyFrame, "domains");
  await emptyFrame.locator("#domain-idea").fill("empty fixture");
  await emptyPage.evaluate(() => window.__testHost.respond("nymrel_find_domain", {structuredContent:{suggestions:[]},content:[]}));
  await emptyFrame.locator("#form-domains button[type=submit]").click();
  await emptyFrame.getByText("No domain ideas were returned.", {exact:false}).waitFor();
  assert.equal(await emptyFrame.locator("#status-domains").getAttribute("data-kind"), "success", "an empty native result remains a successful measurement");
  await chooseTool(emptyFrame, "golf");
  await emptyFrame.locator(".club-name").fill("7 iron");
  await emptyFrame.locator(".club-carry").fill("165");
  await emptyPage.evaluate(() => window.__testHost.respond("nymrel_golf_bag_gap", {structuredContent:{average_gap_yards:0,problem_gaps:[],recommendations:[]},content:[]}));
  await emptyFrame.locator("#form-golf button[type=submit]").click();
  await emptyFrame.getByText("One club was submitted.", {exact:false}).waitFor();
  await emptyFrame.getByText("No problem gaps were reported.").waitFor();
  await emptyPage.close();

  const rowPage = await browser.newPage({viewport:{width:320,height:780}});
  await rowPage.goto(base);
  const rowFrame = rowPage.frameLocator("#workbench-frame");
  await rowFrame.locator("#workbench").waitFor({state:"visible"});
  await chooseTool(rowFrame, "golf");
  for (let index=0; index<13; index++) await rowFrame.locator("#add-club").click();
  assert.equal(await rowFrame.locator("#add-club").isDisabled(), true, "golf limits the bag to fourteen clubs");
  let rows = rowFrame.locator(".club-row");
  for (let index=0; index<14; index++) {
    await rows.nth(index).locator(".club-name").fill(`Club ${index + 1}`);
    await rows.nth(index).locator(".club-carry").fill(String(110 + index * 10));
  }
  await rows.nth(0).locator(".club-carry").fill("401");
  await rowFrame.locator("#form-golf button[type=submit]").click();
  assert.equal(await rows.nth(0).locator(".club-carry").evaluate((element) => element === document.activeElement), true);
  assert.equal(await getHost(rowPage, "window.__testHost.calls.length"), 0);
  await rows.nth(0).locator(".club-carry").fill("110");
  await rows.nth(0).locator(".club-loft").fill("81");
  await rowFrame.locator("#form-golf button[type=submit]").click();
  assert.equal(await rows.nth(0).locator(".club-loft").evaluate((element) => element === document.activeElement), true);
  await rows.nth(0).locator(".club-loft").fill("30.5");
  await rowFrame.locator("#form-golf button[type=submit]").click();
  await rowFrame.locator("#status-golf").getByText("Result ready.", {exact:false}).waitFor();
  assert.equal((await getHost(rowPage, "window.__testHost.calls.at(-1).arguments.clubs")).length, 14);
  await rows.nth(0).locator(".remove-club").focus();
  await rows.nth(0).locator(".remove-club").press("Enter");
  rows = rowFrame.locator(".club-row");
  assert.equal(await rows.nth(0).locator(".club-name").evaluate((element) => element === document.activeElement), true, "removing a club keeps keyboard focus at the next editable row");
  assert.equal(await rows.nth(0).locator(".club-name").getAttribute("aria-label"), "Club 1 name", "removing a row updates accessible field positions");
  assert.equal(await rowFrame.locator("#add-club").isDisabled(), false);
  assert.ok(await rowFrame.locator("body").evaluate((body) => body.scrollWidth <= body.clientWidth + 1));
  await rowPage.close();

  const preferencePage = await browser.newPage();
  await preferencePage.goto(base);
  let preferenceFrame = preferencePage.frameLocator("#workbench-frame");
  await preferenceFrame.locator("#workbench").waitFor({state:"visible"});
  await preferenceFrame.locator("#settings summary").click();
  await preferenceFrame.locator("#default-tool").selectOption("clip");
  await preferenceFrame.locator("#default-platform").selectOption("instagram_reels");
  await preferencePage.reload();
  preferenceFrame = preferencePage.frameLocator("#workbench-frame");
  await preferenceFrame.locator("#workbench").waitFor({state:"visible"});
  assert.equal(await preferenceFrame.locator("#tab-clip").getAttribute("aria-selected"), "true");
  assert.equal(await preferenceFrame.locator("#clip-platform").inputValue(), "instagram_reels");
  assert.equal(await preferenceFrame.locator("#clip-transcript").inputValue(), "", "returning to the app restores display preferences without saved form data");
  assert.equal(await getHost(preferencePage, "window.__testHost.calls.length"), 0);
  await preferencePage.close();

  const deadlinePage = await browser.newPage();
  await deadlinePage.goto(`${base}/?mode=tool-timeout`);
  const deadlineFrame = deadlinePage.frameLocator("#workbench-frame");
  await deadlineFrame.locator("#workbench").waitFor({state:"visible"});
  await deadlineFrame.locator("#website-url").fill("https://example.test");
  await deadlineFrame.locator("#form-website button[type=submit]").click();
  await deadlineFrame.locator("#status-website").getByText("Nymrel did not respond in time.", {exact:false}).waitFor({timeout:35000});
  assert.equal(await deadlineFrame.locator("#form-website button[type=submit]").isDisabled(), false);
  assert.equal(await deadlineFrame.locator("#result").isVisible(), false);
  await deadlinePage.evaluate(() => { window.__testHost.dropTools=false; });
  await deadlineFrame.locator("#form-website button[type=submit]").click();
  await deadlineFrame.locator("#status-website").getByText("Result ready.", {exact:false}).waitFor();
  await deadlinePage.evaluate(() => { window.__testHost.dropContext=true; });
  await deadlineFrame.getByRole("button", {name:"Use result in conversation"}).click();
  await deadlineFrame.locator('[data-testid="share-status"]').getByText("This host could not add the result summary.", {exact:false}).waitFor({timeout:10000});
  assert.equal(await deadlineFrame.getByRole("button", {name:"Use result in conversation"}).isDisabled(), false, "the actual SDK handoff deadline leaves retry available");
  await deadlinePage.close();

  for (const [legacyPlatform, currentPlatform] of [["reels", "instagram_reels"], ["shorts", "youtube_shorts"]]) {
    const migrationPage = await browser.newPage();
    await migrationPage.addInitScript((platform) => {
      localStorage.setItem("nymrel-workbench-preferences-v1", JSON.stringify({ defaultTool: "clip", platform, showEvidence: false }));
    }, legacyPlatform);
    await migrationPage.goto(base);
    const migrationFrame = migrationPage.frameLocator("#workbench-frame");
    await migrationFrame.locator("#workbench").waitFor({ state: "visible", timeout: 10000 });
    assert.equal(await migrationFrame.locator("#default-platform").inputValue(), currentPlatform, `saved ${legacyPlatform} preference migrates to ${currentPlatform}`);
    await migrationPage.close();
  }

  const timeoutPage = await browser.newPage();
  await timeoutPage.goto(`${base}/?mode=timeout`);
  const timeoutFrame = timeoutPage.frameLocator("#workbench-frame");
  await timeoutFrame.getByText("The Nymrel workbench could not connect to its host.").waitFor({ timeout: 9000 });
  await timeoutPage.close();
  const reconnectPage = await browser.newPage();
  await reconnectPage.goto(`${base}/?mode=reconnect`);
  const reconnectFrame = reconnectPage.frameLocator("#workbench-frame");
  await reconnectFrame.getByRole("button", {name:"Reconnect",exact:true}).waitFor({timeout:9000});
  await reconnectFrame.getByRole("button", {name:"Reconnect",exact:true}).click();
  await reconnectFrame.locator("#workbench").waitFor({state:"visible"});
  assert.equal(await getHost(reconnectPage, "window.__testHost.initializeAttempts"), 2);
  assert.equal(await getHost(reconnectPage, "window.__testHost.calls.length"), 0, "reconnect does not execute a tool");
  await reconnectPage.close();
  await disabledPage.close();
  await deepPage.close();
  await page.close();
  process.stdout.write("workbench UI smoke passed: SDK handshake, four public tools, focused validation, retained results after service/transport/timeout/malformed failures, submitted input provenance, explicit conversation context, keyboard, 320px layout, preferences, capabilities, and deep links\n");
} finally {
  if (browser) await browser.close();
  await new Promise((resolve) => server.close(resolve));
}
