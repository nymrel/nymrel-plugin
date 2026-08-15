import assert from "node:assert/strict";
import test from "node:test";
import {
  AuditTargetError,
  auditWebsite,
  finalizeAuditReport,
  isPublicIp,
  verifyAuditReport,
} from "../dist/audit.js";

const PUBLIC_DNS = async () => [{ address: "93.184.216.34", family: 4 }];
const FIXED_ID = "5fe5ea67-2df4-4058-a3a2-e61f7ae2d52f";
const FIXED_DATE = new Date("2026-08-14T22:00:00.000Z");

const completeHtml = `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Complete public website audit fixture</title>
    <meta name="description" content="A deliberately complete public webpage fixture with enough descriptive context to test the Nymrel Website Audit safely and repeatably.">
    <link rel="canonical" href="https://good.example/">
    <meta property="og:title" content="Complete fixture">
    <meta property="og:description" content="A complete sharing preview fixture.">
    <meta property="og:image" content="https://good.example/preview.png">
    <script type="application/ld+json">{"@context":"https://schema.org","@type":"WebPage","name":"Complete fixture"}</script>
  </head>
  <body><h1>Complete fixture</h1><img src="hero.png" alt="A test landscape"></body>
</html>`;

function mappedFetcher(entries) {
  return async (input) => {
    const key = input.toString();
    const entry = entries[key] ?? { body: "not found", status: 404, headers: { "content-type": "text/plain" } };
    return new Response(entry.body ?? "", {
      status: entry.status ?? 200,
      headers: entry.headers ?? { "content-type": "text/html; charset=utf-8" },
    });
  };
}

test("audits a complete public page and signs a structured report", async () => {
  const report = await auditWebsite("good.example", {
    fetcher: mappedFetcher({
      "https://good.example/": { body: completeHtml },
      "https://good.example/robots.txt": { body: "User-agent: *\nAllow: /", headers: { "content-type": "text/plain" } },
      "https://good.example/sitemap.xml": { body: "<urlset></urlset>", headers: { "content-type": "application/xml" } },
      "https://good.example/llms.txt": { body: "# Good Example", headers: { "content-type": "text/plain" } },
    }),
    resolveHost: PUBLIC_DNS,
    now: () => FIXED_DATE,
    idFactory: () => FIXED_ID,
  });

  assert.equal(report.target.requestedUrl, "https://good.example/");
  assert.equal(report.technical.httpStatus, 200);
  assert.equal(report.findings.length, 14);
  assert.ok(report.summary.score >= 90);
  assert.equal(report.summary.grade, "A");
  assert.equal(report.topPriorities.length, 0);
  assert.equal(report.technical.fetchedAt, FIXED_DATE.toISOString());
  assert.match(report.reportDigest, /^sha256:[a-f0-9]{64}$/);
  assert.equal(verifyAuditReport(report), true);
});

test("prioritizes missing core signals for a plain page", async () => {
  const report = await auditWebsite("https://thin.example/", {
    fetcher: mappedFetcher({
      "https://thin.example/": {
        body: "<!doctype html><html><head></head><body><img src='missing-alt.png'></body></html>",
      },
    }),
    resolveHost: PUBLIC_DNS,
    now: () => FIXED_DATE,
    idFactory: () => FIXED_ID,
  });

  assert.ok(report.summary.score < 60);
  assert.equal(report.summary.grade, "F");
  assert.equal(report.topPriorities.length, 3);
  assert.ok(report.topPriorities.some((item) => item.findingId === "page-title"));
  assert.ok(report.topPriorities.some((item) => item.findingId === "primary-heading"));
});

test("rejects private and reserved network targets before fetch", async () => {
  let fetchCalls = 0;
  await assert.rejects(
    () =>
      auditWebsite("http://127.0.0.1/admin", {
        fetcher: async () => {
          fetchCalls += 1;
          return new Response("unexpected");
        },
      }),
    (error) => error instanceof AuditTargetError && /private|reserved|local/i.test(error.message),
  );
  assert.equal(fetchCalls, 0);
});

test("revalidates redirects and blocks a public-to-private redirect", async () => {
  const fetcher = mappedFetcher({
    "https://redirect.example/": {
      status: 302,
      headers: { location: "http://10.0.0.5/secret", "content-type": "text/plain" },
    },
  });
  await assert.rejects(
    () => auditWebsite("https://redirect.example/", { fetcher, resolveHost: PUBLIC_DNS }),
    (error) => error instanceof AuditTargetError && /private|reserved|local/i.test(error.message),
  );
});

test("rejects oversized pages from content-length before parsing", async () => {
  const fetcher = async () =>
    new Response("small body", {
      headers: { "content-type": "text/html", "content-length": "1000001" },
    });
  await assert.rejects(
    () => auditWebsite("https://large.example/", { fetcher, resolveHost: PUBLIC_DNS }),
    (error) => error instanceof AuditTargetError && /larger/i.test(error.message),
  );
});

test("detects a changed report before rendering", async () => {
  const original = await auditWebsite("https://good.example/", {
    fetcher: mappedFetcher({
      "https://good.example/": { body: completeHtml },
      "https://good.example/robots.txt": { body: "ok", headers: { "content-type": "text/plain" } },
      "https://good.example/sitemap.xml": { body: "ok", headers: { "content-type": "application/xml" } },
      "https://good.example/llms.txt": { body: "ok", headers: { "content-type": "text/plain" } },
    }),
    resolveHost: PUBLIC_DNS,
    now: () => FIXED_DATE,
    idFactory: () => FIXED_ID,
  });
  const changed = structuredClone(original);
  changed.summary.score -= 1;
  assert.equal(verifyAuditReport(changed), false);
  const { reportDigest: _ignored, ...input } = changed;
  assert.equal(verifyAuditReport(finalizeAuditReport(input)), true);
});

test("public IP classifier blocks common SSRF ranges", () => {
  assert.equal(isPublicIp("93.184.216.34"), true);
  for (const address of ["0.0.0.0", "10.0.0.1", "100.64.0.1", "127.0.0.1", "169.254.1.1", "172.16.0.1", "192.168.1.1", "::1", "fd00::1", "fe80::1"]) {
    assert.equal(isPublicIp(address), false, address);
  }
});
