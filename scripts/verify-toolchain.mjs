import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (path) => readFileSync(new URL(`../${path}`, import.meta.url), "utf8");
const packageJson = JSON.parse(read("package.json"));

assert.equal(read(".node-version").trim(), "24.20.0", ".node-version must pin Node 24.20.0");
assert.equal(packageJson.engines.node, ">=22 <25");
assert.equal(packageJson.packageManager, "npm@11.19.1");
assert.deepEqual(packageJson.devEngines, {
  runtime: { name: "node", version: ">=22 <25", onFail: "error" },
  packageManager: { name: "npm", version: "11.19.1", onFail: "error" },
});
assert.deepEqual(packageJson.allowScripts, { "esbuild@0.28.2": true });

const npmrc = new Set(read(".npmrc").trim().split(/\r?\n/u));
for (const required of [
  "engine-strict=true",
  "strict-allow-scripts=true",
  "strict-peer-deps=true",
]) {
  assert(npmrc.has(required), `.npmrc must contain ${required}`);
}

const nodeMajor = Number.parseInt(process.versions.node.split(".")[0], 10);
assert([22, 24].includes(nodeMajor), `Node ${process.versions.node} is outside the reviewed 22/24 lines`);

const npmUserAgent = process.env.npm_config_user_agent ?? "";
assert.match(npmUserAgent, /(?:^|\s)npm\/11\.19\.1(?:\s|$)/u, "npm 11.19.1 is required");

const runtimeRequirements = read("hosted-mcp/requirements.txt").trim().split(/\r?\n/u);
assert.deepEqual(runtimeRequirements, ["fastmcp==3.4.7", "requests==2.34.2"]);

const pyproject = read("hosted-mcp/pyproject.toml");
for (const marker of [
  'requires-python = ">=3.13,<3.14"',
  '"fastmcp==3.4.7"',
  '"requests==2.34.2"',
  'target-version = "py313"',
]) {
  assert(pyproject.includes(marker), `hosted-mcp/pyproject.toml must contain ${marker}`);
}

console.log("Toolchain contract verified: Node 22/24, npm 11.19.1, Python 3.13.");
