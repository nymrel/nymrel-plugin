import { createHash, randomUUID } from "node:crypto";
import { lookup } from "node:dns/promises";
import { isIP } from "node:net";
import { performance } from "node:perf_hooks";
import { load } from "cheerio";
import {
  auditReportSchema,
  type AuditFinding,
  type AuditPriority,
  type AuditReport,
  type AuditReportInput,
} from "./schema.js";

const MAX_PAGE_BYTES = 1_000_000;
const MAX_PROBE_BYTES = 128_000;
const REQUEST_TIMEOUT_MS = 8_000;
const MAX_REDIRECTS = 3;

type LookupAddress = { address: string; family: number };
type ResolveHost = (hostname: string) => Promise<LookupAddress[]>;
type FetchLike = (input: string | URL, init?: RequestInit) => Promise<Response>;

export type AuditDependencies = {
  fetcher?: FetchLike;
  resolveHost?: ResolveHost;
  now?: () => Date;
  idFactory?: () => string;
};

type SafeFetchResult = {
  body: string;
  bytes: number;
  finalUrl: URL;
  status: number;
  contentType: string;
  elapsedMs: number;
  checkedUrls: string[];
};

type ProbeResult = {
  ok: boolean;
  url: string;
  status: number;
};

export class AuditTargetError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "AuditTargetError";
  }
}

const defaultResolveHost: ResolveHost = async (hostname) =>
  lookup(hostname, { all: true, verbatim: true });

function normalizeUrl(raw: string): URL {
  const trimmed = raw.trim();
  if (!trimmed) throw new AuditTargetError("Enter a public website URL to audit.");

  const candidate = /^[a-z][a-z0-9+.-]*:\/\//i.test(trimmed)
    ? trimmed
    : `https://${trimmed}`;

  let url: URL;
  try {
    url = new URL(candidate);
  } catch {
    throw new AuditTargetError("That does not look like a valid public website URL.");
  }

  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new AuditTargetError("Nymrel audits public HTTP or HTTPS webpages only.");
  }
  if (url.username || url.password) {
    throw new AuditTargetError("Remove usernames or passwords from the URL before auditing it.");
  }
  if (url.port && url.port !== "80" && url.port !== "443") {
    throw new AuditTargetError("Nymrel audits public web ports 80 and 443 only.");
  }

  url.hash = "";
  return url;
}

function isBlockedIpv4(address: string): boolean {
  const octets = address.split(".").map(Number);
  if (octets.length !== 4 || octets.some((value) => !Number.isInteger(value))) return true;
  const [a = 0, b = 0] = octets;
  return (
    a === 0 ||
    a === 10 ||
    a === 127 ||
    (a === 100 && b >= 64 && b <= 127) ||
    (a === 169 && b === 254) ||
    (a === 172 && b >= 16 && b <= 31) ||
    (a === 192 && b === 0) ||
    (a === 192 && b === 168) ||
    (a === 192 && b === 2) ||
    (a === 198 && (b === 18 || b === 19 || b === 51)) ||
    (a === 203 && b === 0) ||
    a >= 224
  );
}

function isBlockedIpv6(address: string): boolean {
  const normalized = address.toLowerCase().split("%")[0] ?? "";
  if (normalized === "::" || normalized === "::1") return true;
  if (normalized.startsWith("fc") || normalized.startsWith("fd")) return true;
  if (/^fe[89ab]/.test(normalized)) return true;
  if (normalized.startsWith("ff")) return true;
  if (normalized.startsWith("2001:db8:")) return true;
  const mapped = normalized.match(/^::ffff:(\d+\.\d+\.\d+\.\d+)$/);
  return mapped ? isBlockedIpv4(mapped[1] ?? "") : false;
}

export function isPublicIp(address: string): boolean {
  const family = isIP(address);
  if (family === 4) return !isBlockedIpv4(address);
  if (family === 6) return !isBlockedIpv6(address);
  return false;
}

async function assertPublicTarget(url: URL, resolveHost: ResolveHost): Promise<void> {
  const hostname = url.hostname.toLowerCase().replace(/\.$/, "");
  if (!hostname || hostname === "localhost" || hostname.endsWith(".localhost")) {
    throw new AuditTargetError("Nymrel cannot access local or private-network websites.");
  }

  if (isIP(hostname)) {
    if (!isPublicIp(hostname)) {
      throw new AuditTargetError("Nymrel cannot access local, private, or reserved network addresses.");
    }
    return;
  }

  let addresses: LookupAddress[];
  try {
    addresses = await resolveHost(hostname);
  } catch {
    throw new AuditTargetError("Nymrel could not resolve that website's public address.");
  }
  if (addresses.length === 0 || addresses.some(({ address }) => !isPublicIp(address))) {
    throw new AuditTargetError("Nymrel cannot access websites that resolve to local, private, or reserved networks.");
  }
}

async function readBody(response: Response, limit: number): Promise<{ body: string; bytes: number }> {
  const declared = Number(response.headers.get("content-length") ?? "0");
  if (Number.isFinite(declared) && declared > limit) {
    throw new AuditTargetError(`The webpage is larger than Nymrel's ${limit.toLocaleString()} byte audit limit.`);
  }

  if (!response.body) return { body: "", bytes: 0 };
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      if (!value) continue;
      total += value.byteLength;
      if (total > limit) {
        throw new AuditTargetError(`The webpage is larger than Nymrel's ${limit.toLocaleString()} byte audit limit.`);
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }

  const merged = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    merged.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return { body: new TextDecoder("utf-8", { fatal: false }).decode(merged), bytes: total };
}

async function safeFetch(
  initialUrl: URL,
  options: {
    fetcher: FetchLike;
    resolveHost: ResolveHost;
    maxBytes: number;
    requireHtml: boolean;
  },
): Promise<SafeFetchResult> {
  const checkedUrls: string[] = [];
  let currentUrl = initialUrl;
  const started = performance.now();

  for (let redirect = 0; redirect <= MAX_REDIRECTS; redirect += 1) {
    await assertPublicTarget(currentUrl, options.resolveHost);
    checkedUrls.push(toDisplayUrl(currentUrl));

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    let response: Response;
    try {
      response = await options.fetcher(currentUrl, {
        method: "GET",
        redirect: "manual",
        signal: controller.signal,
        headers: {
          accept: options.requireHtml
            ? "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1"
            : "text/plain,application/xml,text/xml;q=0.9,*/*;q=0.1",
          "user-agent": "NymrelWebsiteAudit/1.0 (+https://nymrel.com/scan)",
        },
      });
    } catch (error) {
      if (error instanceof AuditTargetError) throw error;
      const detail = error instanceof Error && error.name === "AbortError" ? "timed out" : "could not be fetched";
      throw new AuditTargetError(`The webpage ${detail}. Check that it is public and try again.`);
    } finally {
      clearTimeout(timeout);
    }

    if (response.status >= 300 && response.status < 400) {
      const location = response.headers.get("location");
      if (!location) throw new AuditTargetError("The webpage returned a redirect without a destination.");
      if (redirect === MAX_REDIRECTS) throw new AuditTargetError("The webpage redirected too many times.");
      currentUrl = new URL(location, currentUrl);
      if (currentUrl.protocol !== "http:" && currentUrl.protocol !== "https:") {
        throw new AuditTargetError("The webpage redirected outside HTTP or HTTPS.");
      }
      continue;
    }

    const contentType = response.headers.get("content-type")?.toLowerCase() ?? "";
    if (options.requireHtml && !contentType.includes("text/html") && !contentType.includes("application/xhtml+xml")) {
      throw new AuditTargetError("That URL did not return an HTML webpage.");
    }
    const { body, bytes } = await readBody(response, options.maxBytes);
    return {
      body,
      bytes,
      finalUrl: currentUrl,
      status: response.status,
      contentType,
      elapsedMs: Math.max(0, Math.round(performance.now() - started)),
      checkedUrls,
    };
  }

  throw new AuditTargetError("The webpage redirected too many times.");
}

function toDisplayUrl(url: URL): string {
  const safe = new URL(url.origin + url.pathname);
  return safe.toString();
}

async function probeFile(
  url: URL,
  fetcher: FetchLike,
  resolveHost: ResolveHost,
): Promise<ProbeResult> {
  try {
    const result = await safeFetch(url, {
      fetcher,
      resolveHost,
      maxBytes: MAX_PROBE_BYTES,
      requireHtml: false,
    });
    return {
      ok: result.status >= 200 && result.status < 300,
      status: result.status,
      url: toDisplayUrl(result.finalUrl),
    };
  } catch {
    return { ok: false, status: 0, url: toDisplayUrl(url) };
  }
}

function finding(
  id: string,
  title: string,
  category: AuditFinding["category"],
  status: AuditFinding["status"],
  priority: AuditFinding["priority"],
  plainEnglish: string,
  evidence: string,
  recommendation: string,
): AuditFinding {
  return { id, title, category, status, priority, plainEnglish, evidence, recommendation };
}

function rankFinding(item: AuditFinding): number {
  const status = item.status === "fail" ? 30 : item.status === "attention" ? 20 : 0;
  const priority = item.priority === "high" ? 3 : item.priority === "medium" ? 2 : 1;
  return status + priority;
}

function summarize(findings: AuditFinding[]): AuditReport["summary"] {
  const weights = { high: 3, medium: 2, low: 1 } as const;
  let earned = 0;
  let possible = 0;
  for (const item of findings) {
    const weight = weights[item.priority];
    possible += weight;
    earned += item.status === "pass" ? weight : item.status === "attention" ? weight * 0.5 : 0;
  }
  const score = possible === 0 ? 0 : Math.round((earned / possible) * 100);
  const passed = findings.filter((item) => item.status === "pass").length;
  const attention = findings.filter((item) => item.status === "attention").length;
  const failed = findings.filter((item) => item.status === "fail").length;
  const grade = score >= 90 ? "A" : score >= 80 ? "B" : score >= 70 ? "C" : score >= 60 ? "D" : "F";
  const verdict =
    score >= 90
      ? "Strong technical foundation. The remaining work is refinement."
      : score >= 75
        ? "A solid base with a few clear visibility improvements."
        : score >= 55
          ? "The page is usable, but important signals are inconsistent or missing."
          : "Core visibility signals need attention before the page can do its best work.";
  return { score, grade, verdict, passed, attention, failed };
}

function stableStringify(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(",")}]`;
  if (value && typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>).sort(([a], [b]) => a.localeCompare(b));
    return `{${entries.map(([key, item]) => `${JSON.stringify(key)}:${stableStringify(item)}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

export function finalizeAuditReport(input: AuditReportInput): AuditReport {
  const reportDigest = `sha256:${createHash("sha256").update(stableStringify(input)).digest("hex")}`;
  return auditReportSchema.parse({ ...input, reportDigest });
}

export function verifyAuditReport(report: AuditReport): boolean {
  const parsed = auditReportSchema.safeParse(report);
  if (!parsed.success) return false;
  const { reportDigest, ...input } = parsed.data;
  return finalizeAuditReport(input).reportDigest === reportDigest;
}

export async function auditWebsite(rawUrl: string, deps: AuditDependencies = {}): Promise<AuditReport> {
  const fetcher = deps.fetcher ?? fetch;
  const resolveHost = deps.resolveHost ?? defaultResolveHost;
  const now = deps.now ?? (() => new Date());
  const idFactory = deps.idFactory ?? randomUUID;
  const requested = normalizeUrl(rawUrl);

  const page = await safeFetch(requested, {
    fetcher,
    resolveHost,
    maxBytes: MAX_PAGE_BYTES,
    requireHtml: true,
  });
  if (page.status < 200 || page.status >= 400) {
    throw new AuditTargetError(`The webpage returned HTTP ${page.status}, so Nymrel could not audit a normal page response.`);
  }

  const origin = page.finalUrl.origin;
  const probeUrls = {
    robots: new URL("/robots.txt", origin),
    sitemap: new URL("/sitemap.xml", origin),
    llms: new URL("/llms.txt", origin),
  };
  const [robots, sitemap, llms] = await Promise.all([
    probeFile(probeUrls.robots, fetcher, resolveHost),
    probeFile(probeUrls.sitemap, fetcher, resolveHost),
    probeFile(probeUrls.llms, fetcher, resolveHost),
  ]);

  const $ = load(page.body);
  const title = $("title").first().text().replace(/\s+/g, " ").trim();
  const description = $('meta[name="description" i]').attr("content")?.replace(/\s+/g, " ").trim() ?? "";
  const canonicalRaw = $('link[rel="canonical" i]').attr("href")?.trim() ?? "";
  const robotsMeta = $('meta[name="robots" i]').attr("content")?.toLowerCase() ?? "";
  const h1Count = $("h1").length;
  const viewport = $('meta[name="viewport" i]').attr("content")?.trim() ?? "";
  const language = $("html").attr("lang")?.trim() ?? "";
  const imageCount = $("img").length;
  const imagesWithAlt = $("img").filter((_, element) => $(element).attr("alt") !== undefined).length;
  const altRatio = imageCount === 0 ? 1 : imagesWithAlt / imageCount;
  const ogTitle = $('meta[property="og:title" i]').attr("content")?.trim() ?? "";
  const ogDescription = $('meta[property="og:description" i]').attr("content")?.trim() ?? "";
  const ogImage = $('meta[property="og:image" i]').attr("content")?.trim() ?? "";
  const jsonLdScripts = $('script[type="application/ld+json" i]')
    .map((_, element) => $(element).text())
    .get();
  const validJsonLd = jsonLdScripts.filter((script) => {
    try {
      JSON.parse(script);
      return true;
    } catch {
      return false;
    }
  }).length;

  const findings: AuditFinding[] = [];
  findings.push(
    finding(
      "secure-transport",
      "Secure transport",
      "access",
      page.finalUrl.protocol === "https:" ? "pass" : "fail",
      "high",
      page.finalUrl.protocol === "https:"
        ? "Visitors and crawlers receive the page over HTTPS."
        : "The page is served without HTTPS, which weakens trust and browser compatibility.",
      `Final protocol: ${page.finalUrl.protocol.replace(":", "").toUpperCase()}`,
      page.finalUrl.protocol === "https:"
        ? "Keep HTTPS redirects and certificate renewal in place."
        : "Serve the page over HTTPS and permanently redirect the HTTP version.",
    ),
    finding(
      "page-title",
      "Page title",
      "search",
      !title ? "fail" : title.length < 15 || title.length > 65 ? "attention" : "pass",
      "high",
      !title
        ? "The page does not give search engines or browser tabs a clear title."
        : "The title is present and gives the page a primary label.",
      title ? `Title length: ${title.length} characters` : "No <title> text found",
      !title
        ? "Add one specific <title> that names the page and its main value."
        : title.length < 15 || title.length > 65
          ? "Tighten the title to roughly 15–65 descriptive characters."
          : "Keep the title unique and aligned with the page's main intent.",
    ),
    finding(
      "meta-description",
      "Search description",
      "search",
      !description ? "fail" : description.length < 70 || description.length > 165 ? "attention" : "pass",
      "medium",
      !description
        ? "The page is missing a concise search-result summary."
        : "A meta description is available for search and sharing systems.",
      description ? `Description length: ${description.length} characters` : "No meta description found",
      !description
        ? "Add a specific meta description that explains the page in one useful sentence."
        : description.length < 70 || description.length > 165
          ? "Rewrite the description to roughly 70–165 useful characters."
          : "Keep it accurate when the page offer changes.",
    ),
    finding(
      "primary-heading",
      "Primary heading",
      "structure",
      h1Count === 1 ? "pass" : h1Count === 0 ? "fail" : "attention",
      "high",
      h1Count === 1
        ? "The page has one clear primary heading."
        : h1Count === 0
          ? "The page has no primary heading to anchor its topic."
          : "Multiple primary headings make the page hierarchy less clear.",
      `H1 elements found: ${h1Count}`,
      h1Count === 1 ? "Keep supporting sections under logical H2/H3 headings." : "Use one descriptive H1, then organize sections with H2 and H3 headings.",
    ),
    finding(
      "canonical-url",
      "Canonical URL",
      "search",
      canonicalRaw ? "pass" : "attention",
      "medium",
      canonicalRaw
        ? "The page declares which URL should represent this content."
        : "The page does not explicitly name its preferred URL.",
      canonicalRaw ? "Canonical link is present" : "No canonical link found",
      canonicalRaw ? "Keep the canonical absolute and aligned with the public production URL." : "Add an absolute rel=canonical link for the preferred public URL.",
    ),
    finding(
      "indexability",
      "Indexing directive",
      "search",
      robotsMeta.includes("noindex") ? "fail" : "pass",
      "high",
      robotsMeta.includes("noindex")
        ? "The page explicitly asks search engines not to index it."
        : "No page-level noindex directive was found.",
      robotsMeta ? `Robots meta: ${robotsMeta.slice(0, 120)}` : "No restrictive robots meta found",
      robotsMeta.includes("noindex") ? "Remove noindex if this page is intended to appear in search." : "Confirm production headers do not add a conflicting X-Robots-Tag.",
    ),
    finding(
      "structured-data",
      "Structured data",
      "ai-readability",
      validJsonLd > 0 ? "pass" : jsonLdScripts.length > 0 ? "fail" : "attention",
      "medium",
      validJsonLd > 0
        ? "Machine-readable JSON-LD helps systems understand the page's entities."
        : "The page has no valid JSON-LD block for machine-readable context.",
      `JSON-LD blocks: ${jsonLdScripts.length}; valid: ${validJsonLd}`,
      validJsonLd > 0 ? "Validate the markup whenever the page's visible facts change." : "Add the smallest accurate Schema.org JSON-LD type supported by the visible page content.",
    ),
    finding(
      "social-preview",
      "Social preview",
      "sharing",
      ogTitle && ogDescription && ogImage ? "pass" : ogTitle || ogDescription || ogImage ? "attention" : "fail",
      "medium",
      ogTitle && ogDescription && ogImage
        ? "The page defines a complete title, description, and image for link previews."
        : "Shared links may inherit incomplete or unpredictable preview content.",
      `Open Graph title: ${Boolean(ogTitle)}; description: ${Boolean(ogDescription)}; image: ${Boolean(ogImage)}`,
      "Provide accurate og:title, og:description, and og:image values that match the page.",
    ),
    finding(
      "image-alternatives",
      "Image text alternatives",
      "access",
      altRatio >= 0.9 ? "pass" : altRatio >= 0.6 ? "attention" : "fail",
      "medium",
      imageCount === 0
        ? "There are no content images to evaluate on this page."
        : altRatio >= 0.9
          ? "Nearly every image declares alternative text, including empty alt for decorative images."
          : "Some images do not declare alternative text.",
      `Images with an alt attribute: ${imagesWithAlt} of ${imageCount}`,
      altRatio >= 0.9 ? "Keep meaningful alt text specific and decorative alt text empty." : "Add useful alt text to meaningful images and alt=\"\" to decorative images.",
    ),
    finding(
      "mobile-viewport",
      "Mobile viewport",
      "access",
      viewport ? "pass" : "attention",
      "medium",
      viewport ? "The page declares a mobile viewport for responsive rendering." : "Mobile browsers may not receive the intended responsive viewport.",
      viewport ? "Viewport meta is present" : "No viewport meta found",
      viewport ? "Keep responsive layouts tested at 375px and 390px." : "Add a standard width=device-width, initial-scale=1 viewport declaration.",
    ),
    finding(
      "page-language",
      "Page language",
      "access",
      language ? "pass" : "attention",
      "low",
      language ? "The page declares a language for browsers and assistive technology." : "The page does not declare its primary language.",
      language ? `HTML lang: ${language}` : "No html[lang] value found",
      language ? "Keep the language code aligned with the visible content." : "Add the correct BCP 47 language code to the <html> element.",
    ),
    finding(
      "robots-file",
      "Robots file",
      "search",
      robots.ok ? "pass" : "attention",
      "low",
      robots.ok ? "A conventional robots.txt file is reachable." : "No reachable robots.txt file was found at the conventional location.",
      robots.ok ? `robots.txt returned HTTP ${robots.status}` : "robots.txt was absent or unreachable",
      robots.ok ? "Review it before launches so important public pages remain crawlable." : "Publish a concise robots.txt if crawlers need explicit guidance.",
    ),
    finding(
      "sitemap-file",
      "XML sitemap",
      "search",
      sitemap.ok ? "pass" : "attention",
      "medium",
      sitemap.ok ? "A conventional XML sitemap is reachable." : "No reachable sitemap.xml was found at the conventional location.",
      sitemap.ok ? `sitemap.xml returned HTTP ${sitemap.status}` : "sitemap.xml was absent or unreachable",
      sitemap.ok ? "Keep canonical public URLs and last-modified dates accurate." : "Publish an XML sitemap or reference its real location from robots.txt.",
    ),
    finding(
      "llms-file",
      "AI guidance file",
      "ai-readability",
      llms.ok ? "pass" : "attention",
      "low",
      llms.ok ? "An llms.txt file provides an optional machine-readable orientation layer." : "No llms.txt file was found; this is optional, not a ranking requirement.",
      llms.ok ? `llms.txt returned HTTP ${llms.status}` : "llms.txt was absent or unreachable",
      llms.ok ? "Keep it short, factual, and linked to canonical source pages." : "Consider llms.txt only after canonical pages, metadata, and structured data are accurate.",
    ),
  );

  const summary = summarize(findings);
  const topPriorities: AuditPriority[] = findings
    .filter((item) => item.status !== "pass")
    .sort((a, b) => rankFinding(b) - rankFinding(a))
    .slice(0, 3)
    .map((item) => ({
      findingId: item.id,
      title: item.title,
      whyItMatters: item.plainEnglish,
      nextStep: item.recommendation,
      priority: item.priority,
    }));

  const checkedUrls = Array.from(
    new Set([...page.checkedUrls, robots.url, sitemap.url, llms.url]),
  ).slice(0, 8);

  return finalizeAuditReport({
    schemaVersion: "1.0",
    auditId: idFactory(),
    target: {
      requestedUrl: toDisplayUrl(requested),
      finalUrl: toDisplayUrl(page.finalUrl),
      origin: `${origin}/`,
      pageTitle: title.slice(0, 160),
    },
    summary,
    topPriorities,
    findings,
    technical: {
      httpStatus: page.status,
      responseTimeMs: page.elapsedMs,
      fetchedAt: now().toISOString(),
      contentBytes: page.bytes,
      checkedUrls,
    },
    disclaimer:
      "Automated point-in-time technical audit of one public page and conventional discovery files. It is not a legal, accessibility, security, ranking, or compliance certification.",
  });
}
