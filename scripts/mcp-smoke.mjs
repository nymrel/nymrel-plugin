import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { setTimeout as delay } from "node:timers/promises";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";

const port = 9300 + Math.floor(Math.random() * 400);
const baseUrl = `http://127.0.0.1:${port}`;
const child = spawn(process.execPath, ["dist/server.js"], {
  cwd: process.cwd(),
  env: { ...process.env, PORT: String(port) },
  stdio: ["ignore", "pipe", "pipe"],
  windowsHide: true,
});

let output = "";
child.stdout.on("data", (chunk) => {
  output += chunk.toString();
});
child.stderr.on("data", (chunk) => {
  output += chunk.toString();
});

async function waitForHealth() {
  for (let attempt = 0; attempt < 40; attempt += 1) {
    if (child.exitCode !== null) throw new Error(`Server exited early (${child.exitCode}): ${output}`);
    try {
      const response = await fetch(`${baseUrl}/healthz`);
      if (response.ok) return;
    } catch {}
    await delay(100);
  }
  throw new Error(`Server did not become healthy: ${output}`);
}

try {
  await waitForHealth();
  const health = await fetch(`${baseUrl}/healthz`).then((response) => response.json());
  assert.equal(health.status, "ok");
  assert.equal(health.mcp, "/mcp");

  const preview = await fetch(`${baseUrl}/preview`);
  assert.equal(preview.status, 200);
  assert.match(await preview.text(), /Nymrel Website Audit/);

  const client = new Client({ name: "nymrel-smoke-client", version: "1.0.0" });
  const transport = new StreamableHTTPClientTransport(new URL(`${baseUrl}/mcp`));
  await client.connect(transport);

  const tools = await client.listTools();
  assert.deepEqual(
    tools.tools.map((tool) => tool.name).sort(),
    ["audit_website", "render_website_audit"],
  );
  const auditTool = tools.tools.find((tool) => tool.name === "audit_website");
  assert.equal(auditTool?.annotations?.readOnlyHint, true);
  assert.equal(auditTool?.annotations?.openWorldHint, true);
  assert.ok(auditTool?.outputSchema);

  const resources = await client.listResources();
  assert.ok(resources.resources.some((resource) => resource.uri === "ui://nymrel/website-audit/v1.html"));

  const blocked = await client.callTool({
    name: "audit_website",
    arguments: { url: "http://127.0.0.1/admin" },
  });
  assert.equal(blocked.isError, true);
  assert.match(JSON.stringify(blocked.content), /private|reserved|local/i);

  await client.close();
  console.log(`MCP smoke passed: ${tools.tools.length} tools, ${resources.resources.length} resource, private-target guard verified.`);
} finally {
  if (child.exitCode === null) {
    child.kill();
    await Promise.race([new Promise((resolve) => child.once("exit", resolve)), delay(2_000)]);
  }
}
