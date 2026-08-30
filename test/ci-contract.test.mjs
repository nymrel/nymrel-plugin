import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (path) => readFileSync(new URL(`../${path}`, import.meta.url), "utf8");
const packageSource = read("package.json");
const packageJson = JSON.parse(packageSource);
const ci = read(".github/workflows/contract-ci.yml");
const codeql = read(".github/workflows/codeql.yml");
const dependabot = read(".github/dependabot.yml");
const vercel = JSON.parse(read("hosted-mcp/vercel.json"));

const checkoutSha = "3d3c42e5aac5ba805825da76410c181273ba90b1";
const setupNodeSha = "820762786026740c76f36085b0efc47a31fe5020";
const setupPythonSha = "5fda3b95a4ea91299a34e894583c3862153e4b97";
const codeqlSha = "cdf488f595d80d6e07e03d4674febd5ab45fa938";

function assertedActionPins(workflow) {
  const uses = [...workflow.matchAll(/^\s*-?\s*uses:\s*([^\s#]+)/gmu)].map((match) => match[1]);
  assert(uses.length > 0, "workflow must use at least one action");
  for (const action of uses) {
    assert.match(action, /^[^@\s]+@[0-9a-f]{40}$/u, `${action} is not pinned to a full commit SHA`);
  }
  return uses;
}

test("contract CI is least privilege and covers exact cross-platform runtimes", () => {
  assert.match(ci, /^permissions:\r?\n\s+contents: read$/mu);
  assert(!ci.includes("pull_request_target"));
  assert(ci.includes("ubuntu-24.04"));
  assert(ci.includes("windows-2025"));
  assert(ci.includes('node: ["22.22.0", "24.20.0"]'));
  assert(ci.includes('python: ["3.13"]'));
  assert(ci.includes("persist-credentials: false"));
  assert(ci.includes("npm install --global npm@11.19.1"));
  assert(ci.includes("run: npm ci"));
  assert(ci.includes("run: npm run verify"));
  assert(ci.includes("run: npm run audit:prod"));
  assert(ci.includes("python -m pip check"));
  assert(ci.includes("python -m ruff check"));
  assert(ci.includes("python -m pytest hosted-mcp/tests -q"));
  assert(ci.includes("python -m pip_audit --strict"));

  const pins = assertedActionPins(ci);
  assert(pins.includes(`actions/checkout@${checkoutSha}`));
  assert(pins.includes(`actions/setup-node@${setupNodeSha}`));
  assert(pins.includes(`actions/setup-python@${setupPythonSha}`));
});

test("CodeQL covers both implementation languages with job-scoped upload permission", () => {
  assert.match(codeql, /^permissions:\r?\n\s+contents: read$/mu);
  assert(codeql.includes("language: [javascript-typescript, python]"));
  assert(codeql.includes("security-events: write"));
  assert(codeql.includes("build-mode: none"));
  assert(codeql.includes("queries: security-extended"));
  assert(!codeql.includes("pull_request_target"));

  const pins = assertedActionPins(codeql);
  assert(pins.includes(`actions/checkout@${checkoutSha}`));
  assert.equal(pins.filter((pin) => pin === `github/codeql-action/init@${codeqlSha}`).length, 1);
  assert.equal(pins.filter((pin) => pin === `github/codeql-action/analyze@${codeqlSha}`).length, 1);
});

test("Dependabot watches npm, Python, and workflow dependencies", () => {
  for (const ecosystem of ["npm", "pip", "github-actions"]) {
    assert(dependabot.includes(`package-ecosystem: ${ecosystem}`));
  }
  assert(dependabot.includes("directory: /hosted-mcp"));
  assert.equal((dependabot.match(/interval: weekly/gu) ?? []).length, 3);
});

test("local package policy is fail closed", () => {
  assert.equal(
    (packageSource.match(/^  "engines": \{$/gmu) ?? []).length,
    1,
    "package.json must declare exactly one top-level engines object",
  );
  assert.equal(packageJson.engines.node, ">=22 <25");
  assert.equal(packageJson.packageManager, "npm@11.19.1");
  assert.equal(packageJson.devEngines.packageManager.onFail, "error");
  assert.deepEqual(packageJson.allowScripts, { "esbuild@0.28.2": true });
  const npmrc = read(".npmrc");
  assert.match(npmrc, /^engine-strict=true$/mu);
  assert.match(npmrc, /^strict-allow-scripts=true$/mu);
  assert.match(npmrc, /^strict-peer-deps=true$/mu);
});

test("Python runtime and test dependencies are explicit", () => {
  const runtime = read("hosted-mcp/requirements.txt");
  const tests = read("hosted-mcp/requirements-test.txt");
  const pyproject = read("hosted-mcp/pyproject.toml");
  assert.equal(runtime.trim().replace(/\r/gu, ""), "fastmcp==3.4.7\nrequests==2.34.2");
  for (const dependency of [
    "pytest==9.1.1",
    "httpx==0.28.1",
    "pip-audit==2.10.1",
    "python-jose[cryptography]==3.5.0",
    "ruff==0.16.5",
  ]) {
    assert(tests.includes(dependency));
  }
  assert(pyproject.includes('requires-python = ">=3.13,<3.14"'));
});

test("the hosted function bundle excludes development-only files", () => {
  const config = vercel.functions["api/index.py"];
  assert.equal(config.maxDuration, 60);
  assert.equal(config.memory, 1024);
  for (const excluded of ["tests/**", "__pycache__/**", ".pytest_cache/**", ".venv/**", "*.md"]) {
    assert(config.excludeFiles.includes(excluded));
  }
});
