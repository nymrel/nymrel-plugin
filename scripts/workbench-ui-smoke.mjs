import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { chromium } from "playwright";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const asset = await readFile(path.join(root, "hosted-mcp", "api", "assets", "workbench.html"), "utf8");
// Contract from nymrel/nymrel src/app/api/v1/tools/_lib/contracts.ts at
// upstream main 814303a9ef52501e477a5ee10517b87debf4cf75.
const acceptedClipPlatforms = new Set(["tiktok", "instagram_reels", "youtube_shorts", "x"]);
for (const notice of [
  "@modelcontextprotocol/ext-apps 1.7.5 (MIT)",
  "@modelcontextprotocol/sdk 1.30.0 (MIT)",
  "zod 4.5.4 (MIT)",
  "zod-to-json-schema 3.25.2 (ISC)",
  "Permission is hereby granted, free of charge",
  "The above copyright notice and this permission notice shall be included",
  "ISC License",
]) assert.ok(asset.includes(notice), `generated asset must retain bundled license text: ${notice}`);
const hostPage = `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Synthetic host</title></head>
<body style="margin:0"><iframe id="workbench-frame" title="Nymrel tool workbench" src="/workbench.html" style="border:0;width:100vw;height:100vh"></iframe>
<script>
(() => {
  const mode = new URL(location.href).searchParams.get('mode') || 'normal';
  const frame = document.getElementById('workbench-frame');
  const state = window.__testHost = {
    calls: [], updates: [], displayRequests: 0, connected: false,
    delays: Object.create(null), queues: Object.create(null),
    opener: {version:'1.0', default_tool:'website', tools:[
      {id:'website',name:'nymrel_audit_website',title:'Website audit',description:'Measure one public page.'},
      {id:'domains',name:'nymrel_find_domain',title:'Domain ideas',description:'Explore available names.'},
      {id:'golf',name:'nymrel_golf_bag_gap',title:'Golf bag gaps',description:'Compare carries.'},
      {id:'clip',name:'nymrel_social_clip_score',title:'Social clip signals',description:'Measure hook signals.'}
    ]},
    capabilities: mode === 'disabled' ? {} : {serverTools:{},updateModelContext:{text:{}}},
    context: {
      theme: 'light', displayMode:'inline', availableDisplayModes:['inline','fullscreen'],
      'openai/deepLink': mode === 'deep' ? {url:'/golf'} : undefined,
      styles:{variables:{'--color-background-primary':'#fffefa','--color-text-primary':'#26362f'}}
    },
    respond(name, result, delay=0) {
      const queue = this.queues[name] || (this.queues[name] = []);
      queue.push({result,delay});
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
    nymrel_social_clip_score:{hook_score:77,hook_strength:'Strong',signals:{opening_word_count:7,opens_with_hook_pattern:true,addresses_viewer:true,has_curiosity_signal:false,opening_contains_number:false,total_word_count:21,platform_word_range:[20,40],total_word_count_in_platform_range:true},suggested_edits:['Try a shorter opening.']}
  };
  window.addEventListener('message', (event) => {
    if (event.source !== frame.contentWindow || event.data?.jsonrpc !== '2.0') return;
    const message = event.data;
    if (!message.method) return;
    const respond = (result) => frame.contentWindow.postMessage({jsonrpc:'2.0',id:message.id,result}, '*');
    if (message.method === 'ui/initialize') {
      if (mode === 'timeout') return;
      state.connected = true;
      respond({protocolVersion:'2025-11-25',hostInfo:{name:'synthetic-host',version:'1'},hostCapabilities:state.capabilities,hostContext:state.context});
    } else if (message.method === 'ui/notifications/initialized') {
      setTimeout(() => state.notify('ui/notifications/tool-result', {structuredContent:state.opener,content:[{type:'text',text:'Tools ready.'}]}), 0);
    } else if (message.method === 'ui/request-display-mode') {
      state.displayRequests += 1;
      state.context.displayMode = message.params.mode;
      respond({mode:message.params.mode});
    } else if (message.method === 'ui/update-model-context') {
      state.updates.push(message.params);
      respond({});
    } else if (message.method === 'tools/call') {
      const name = message.params?.name;
      const queue = state.queues[name] || [];
      const next = queue.shift();
      const fixture = next || {result:{structuredContent:defaults[name] || {},content:[{type:'text',text:'ok'}]}};
      state.calls.push({name,arguments:message.params?.arguments || {}});
      setTimeout(() => respond(fixture.result), fixture.delay || 0);
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
  assert.equal(await getHost(page, "window.__testHost.calls.length"), beforeWebsite, "credential-bearing URLs are rejected locally");
  await page.evaluate(() => window.__testHost.respond("nymrel_audit_website", {structuredContent:{score:84,grade:"B",ai_discoverability_status:"Readable",recommendations:["<img src=x onerror=window.__injected=1> measured recommendation"],schema_detected:["Product"],full_report_url:"https://example.test/report"},content:[{type:"text",text:"Website audit result"}]}, 900));
  await frame.locator("#website-url").fill("https://example.test");
  await frame.locator("#form-website button[type=submit]").click();
  await frame.getByText("Checking the public page…").waitFor();
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
  await page.evaluate(() => window.__testHost.respond("nymrel_social_clip_score", {structuredContent:{hook_score:77,hook_strength:"Strong",signals:{opening_word_count:7,opens_with_hook_pattern:true,addresses_viewer:true,has_curiosity_signal:false,opening_contains_number:false,total_word_count:21,platform_word_range:[20,40],total_word_count_in_platform_range:true},suggested_edits:["Try a shorter opening."]},content:[{type:"text",text:"clip result"}]}, 700));
  await frame.locator("#form-clip button[type=submit]").click();
  await frame.getByText("Measuring the opening…").waitFor();
  assert.equal(await frame.locator("#form-clip button[type=submit]").isDisabled(), true, "an in-flight tool call cannot be duplicated");
  await chooseTool(frame, "golf");
  await frame.getByText("Average gap").waitFor();
  await page.waitForTimeout(800);
  assert.equal(await frame.locator("#tab-golf").getAttribute("aria-selected"), "true", "a late response does not steal the active tool view");
  await chooseTool(frame, "clip");
  await frame.getByText("77 / 100").waitFor();
  assert.deepEqual(await getHost(page, "window.__testHost.calls.at(-1).arguments"), {transcript_text:"Stop doing this in Python right now.",target_platform:"youtube_shorts"});
  const clipSuccess = {structuredContent:{hook_score:77,hook_strength:"Strong",signals:{opening_word_count:7,opens_with_hook_pattern:true,addresses_viewer:true,has_curiosity_signal:false,opening_contains_number:false,total_word_count:21,platform_word_range:[20,40],total_word_count_in_platform_range:true},suggested_edits:["Try a shorter opening."]},content:[{type:"text",text:"clip result"}]};
  for (const platform of clipPlatformValues) {
    await frame.locator("#clip-platform").selectOption(platform);
    await page.evaluate((result) => window.__testHost.respond("nymrel_social_clip_score", result, 40), clipSuccess);
    await frame.locator("#form-clip button[type=submit]").click();
    await frame.getByText("Measuring the opening…").waitFor();
    await frame.locator("#status-clip").getByText("Result ready.", { exact: false }).waitFor();
    await frame.getByText("77 / 100").waitFor();
    assert.deepEqual(await getHost(page, "window.__testHost.calls.at(-1).arguments"), {
      transcript_text:"Stop doing this in Python right now.", target_platform:platform,
    }, `${platform} must be sent exactly as accepted by the public API`);
  }

  await page.evaluate(() => window.__testHost.respond("nymrel_find_domain", {isError:true,structuredContent:{status:"error",error:{code:"UPSTREAM_NOT_DEPLOYED",message:"Nymrel could not check this idea right now."}},content:[{type:"text",text:"Nymrel could not check this idea right now."}]}));
  await chooseTool(frame, "domains");
  await frame.locator("#form-domains button[type=submit]").click();
  await frame.getByText("Nymrel could not check this idea right now.", { exact: true }).waitFor();
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
  await disabledPage.close();
  await deepPage.close();
  await page.close();
  process.stdout.write("workbench UI smoke passed: SDK handshake, opener result, four public calls, validation, errors/retry, context, preferences, display mode, capability fallback, deep links, and mobile layout\n");
} finally {
  if (browser) await browser.close();
  await new Promise((resolve) => server.close(resolve));
}
