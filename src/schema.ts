import { z } from "zod";

export const findingStatusSchema = z.enum(["pass", "attention", "fail"]);
export const findingPrioritySchema = z.enum(["high", "medium", "low"]);

export const auditFindingSchema = z.object({
  id: z.string().min(1).max(64),
  title: z.string().min(1).max(120),
  category: z.enum(["access", "search", "sharing", "structure", "ai-readability"]),
  status: findingStatusSchema,
  priority: findingPrioritySchema,
  plainEnglish: z.string().min(1).max(280),
  evidence: z.string().min(1).max(280),
  recommendation: z.string().min(1).max(360),
});

export const auditPrioritySchema = z.object({
  findingId: z.string().min(1).max(64),
  title: z.string().min(1).max(120),
  whyItMatters: z.string().min(1).max(280),
  nextStep: z.string().min(1).max(360),
  priority: findingPrioritySchema,
});

export const auditReportSchema = z.object({
  schemaVersion: z.literal("1.0"),
  auditId: z.string().uuid(),
  reportDigest: z.string().regex(/^sha256:[a-f0-9]{64}$/),
  target: z.object({
    requestedUrl: z.string().url(),
    finalUrl: z.string().url(),
    origin: z.string().url(),
    pageTitle: z.string().max(160),
  }),
  summary: z.object({
    score: z.number().int().min(0).max(100),
    grade: z.enum(["A", "B", "C", "D", "F"]),
    verdict: z.string().min(1).max(220),
    passed: z.number().int().min(0),
    attention: z.number().int().min(0),
    failed: z.number().int().min(0),
  }),
  topPriorities: z.array(auditPrioritySchema).max(3),
  findings: z.array(auditFindingSchema).min(1).max(24),
  technical: z.object({
    httpStatus: z.number().int().min(100).max(599),
    responseTimeMs: z.number().int().min(0),
    fetchedAt: z.string().datetime(),
    contentBytes: z.number().int().min(0),
    checkedUrls: z.array(z.string().url()).min(1).max(8),
  }),
  disclaimer: z.string().min(1).max(360),
});

export type AuditFinding = z.infer<typeof auditFindingSchema>;
export type AuditPriority = z.infer<typeof auditPrioritySchema>;
export type AuditReport = z.infer<typeof auditReportSchema>;
export type AuditReportInput = Omit<AuditReport, "reportDigest">;
