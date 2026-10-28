import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { runInNewContext } from "node:vm";

const read = (path) => readFileSync(new URL(`../${path}`, import.meta.url), "utf8");
const packageSource = read("package.json");
const packageJson = JSON.parse(packageSource);
const ci = read(".github/workflows/contract-ci.yml");
const codeql = read(".github/workflows/codeql.yml");
const dependabot = read(".github/dependabot.yml");
const vercel = JSON.parse(read("hosted-mcp/vercel.json"));

const checkoutSha = "3d3c42e5aac5ba805825da76410c181273ba90b1";
const setupNodeSha = "949feb2413d6458794dcd2491c4babbbce0c15c1";
const setupPythonSha = "6d4fd22b20465ccc0f7354476588e8df7c9ca0e0";
const codeqlSha = "9b3254085494b55a0f7c4c2b3d2d52cc712ce370";

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
  assert(!ci.includes("cache: npm"), "setup-node must not invoke npm before the reviewed toolchain");
  assert.equal(
    (ci.match(/package-manager-cache: false/gu) ?? []).length,
    1,
    "the Node bootstrap must explicitly disable setup-node's implicit npm cache",
  );
  assert(
    ci.indexOf("package-manager-cache: false") < ci.indexOf("corepack npm@11.19.1 --version"),
    "the cache boundary must be declared before npm 11.19.1 is activated",
  );
  assert(!ci.includes("npm install --global"));
  assert(ci.includes("run: corepack npm@11.19.1 ci"));
  assert(ci.includes("run: corepack npm@11.19.1 run verify"));
  assert(ci.includes("run: corepack npm@11.19.1 audit --audit-level=high"));
  assert(ci.includes("run: corepack npm@11.19.1 audit --omit=dev --audit-level=high"));
  assert(ci.includes("python -m pip check"));
  assert(ci.includes("python -m ruff check"));
  assert(ci.includes("python -m pytest hosted-mcp/tests -q"));
  assert(ci.includes("python -m pip_audit --strict"));

  const pins = assertedActionPins(ci);
  assert(pins.includes(`actions/checkout@${checkoutSha}`));
  assert(pins.includes(`actions/setup-node@${setupNodeSha}`));
  assert(pins.includes(`actions/setup-python@${setupPythonSha}`));
});

test("live MCP verification requires an explicit request and runs on one existing runner", () => {
  assert.match(ci, /^  push:\r?\n    branches: \[main\]\r?\n    tags: \["verify-live-mcp-\*"\]$/mu);
  assert.match(
    ci,
    /^  workflow_dispatch:\r?\n    inputs:\r?\n      verify_live_remote_read:\r?\n        description: [^\r\n]+\r?\n        type: boolean\r?\n        required: false\r?\n        default: false$/mu,
  );
  assert.equal((ci.match(/verify_live_contract\.py/gu) ?? []).length, 1);

  const pythonJob = ci.split(/\r?\n  hosted-mcp-contract:\r?\n/u)[1];
  assert(pythonJob, "the live check must stay in the existing Python job");
  const step = pythonJob.match(
    /^      - name: [^\r\n]+\r?\n        if: >-\r?\n(?<guard>(?:          [^\r\n]*\r?\n)+)        run: >-\r?\n(?<command>(?:          [^\r\n]+\r?\n)+)/mu,
  );
  assert(step, "the live command needs an explicit step guard");
  assert.equal(
    step.groups.command.trim().replace(/\s+/gu, " "),
    "python hosted-mcp/scripts/verify_live_contract.py https://mcp.nymrel.com --remote-read --issuer https://nymrel-remote-production.up.railway.app",
  );
  const expression = step.groups.guard.trim().replace(/^\$\{\{\s*|\s*\}\}$/gu, "");
  const selected = (event, ref, requested, os = "ubuntu-24.04", python = "3.13") => Boolean(
    runInNewContext(expression, {
      github: { event_name: event, ref },
      inputs: { verify_live_remote_read: requested },
      matrix: { os, python },
      // GitHub's startsWith compares strings without case sensitivity.
      startsWith: (value, prefix) => value.toLowerCase().startsWith(prefix.toLowerCase()),
    }, { timeout: 100 }),
  );

  for (const [event, ref, requested, expected] of [
    ["push", "refs/heads/main", undefined, false],
    ["push", "refs/heads/main", true, false],
    ["pull_request", "refs/pull/49/merge", true, false],
    ["pull_request", "refs/tags/verify-live-mcp-test", true, false],
    ["workflow_dispatch", "refs/heads/main", false, false],
    ["workflow_dispatch", "refs/heads/main", undefined, false],
    ["workflow_dispatch", "refs/tags/verify-live-mcp-test", false, false],
    ["push", "refs/heads/verify-live-mcp-test", undefined, false],
    ["push", "refs/tags/v1.2.0", undefined, false],
    ["push", "refs/tags/verify-live-mcp2-test", undefined, false],
    ["push", "refs/tags/other-verify-live-mcp-test", undefined, false],
    ["push", "refs/tags/verify-live-mcp-test", undefined, true],
    ["workflow_dispatch", "refs/heads/main", true, true],
  ]) {
    assert.equal(selected(event, ref, requested), expected, `${event} ${ref} opt-in=${requested}`);
  }

  const operatingSystems = pythonJob.match(/^        os: \[([^\r\n]+)\]$/mu)[1]
    .split(",").map((os) => os.trim().replace(/^"|"$/gu, ""));
  const pythonVersions = JSON.parse(pythonJob.match(/^        python: (\[[^\r\n]+\])$/mu)[1]);
  for (const [event, ref, requested] of [
    ["push", "refs/tags/verify-live-mcp-test", undefined],
    ["workflow_dispatch", "refs/heads/main", true],
  ]) {
    const runners = operatingSystems.flatMap((os) => pythonVersions.map((python) => ({ os, python })));
    assert.equal(runners.filter(({ os, python }) => selected(event, ref, requested, os, python)).length, 1);
    assert.equal(selected(event, ref, requested, "windows-2025"), false);
    assert.equal(selected(event, ref, requested, "ubuntu-24.04", "3.14"), false);
  }
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
  assert.equal(runtime.trim().replace(/\r/gu, ""), "fastmcp==3.4.10\nrequests==2.34.2");
  for (const dependency of [
    "pytest==9.1.1",
    "httpx==0.28.1",
    "pip-audit==2.10.1",
    "PyJWT[crypto]==2.15.1",
    "ruff==0.17.2",
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
