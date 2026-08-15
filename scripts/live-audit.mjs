import assert from "node:assert/strict";
import { auditWebsite, verifyAuditReport } from "../dist/audit.js";

const report = await auditWebsite("https://example.com");
assert.equal(report.technical.httpStatus, 200);
assert.equal(report.target.origin, "https://example.com/");
assert.equal(report.findings.length, 14);
assert.equal(verifyAuditReport(report), true);
console.log(
  JSON.stringify(
    {
      target: report.target.finalUrl,
      grade: report.summary.grade,
      score: report.summary.score,
      findings: report.findings.length,
      priorities: report.topPriorities.map((item) => item.findingId),
    },
    null,
    2,
  ),
);
