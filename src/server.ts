import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import {
  registerAppResource,
  registerAppTool,
  RESOURCE_MIME_TYPE,
} from "@modelcontextprotocol/ext-apps/server";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import { z } from "zod";
import { AuditTargetError, auditWebsite, verifyAuditReport } from "./audit.js";
import { auditReportSchema, type AuditReport } from "./schema.js";

const VERSION = "1.2.0";
const MCP_PATH = "/mcp";
const WIDGET_URI = "ui://nymrel/website-audit/v1.html";
const widgetHtml = readFileSync(new URL("../public/audit-widget.html", import.meta.url), "utf8");
const previewReport = JSON.parse(
  readFileSync(new URL("../public/preview-report.json", import.meta.url), "utf8"),
) as AuditReport;

const auditInputSchema = {
  url: z
    .string()
    .min(1)
    .max(2_048)
    .describe("Public webpage URL or hostname to audit. Nymrel adds https:// when the scheme is omitted."),
};

function reportText(report: AuditReport): string {
  const priorities = report.topPriorities.length
    ? report.topPriorities.map((item, index) => `${index + 1}. ${item.title}: ${item.nextStep}`).join("\n")
    : "No failed or attention findings were returned.";
  return [
    `Nymrel Website Audit: ${report.target.finalUrl}`,
    `Grade ${report.summary.grade} · ${report.summary.score}/100 · ${report.summary.passed} passed · ${report.summary.attention} need attention · ${report.summary.failed} failed`,
    report.summary.verdict,
    "Top priorities:",
    priorities,
    report.disclaimer,
  ].join("\n");
}

function errorResult(error: unknown) {
  const message =
    error instanceof AuditTargetError
      ? error.message
      : "Nymrel could not complete this audit. Confirm the page is public and try again.";
  return {
    isError: true,
    content: [{ type: "text" as const, text: message }],
  };
}

export function createNymrelMcpServer(): McpServer {
  const server = new McpServer(
    { name: "nymrel-website-audit", version: VERSION },
    {
      instructions:
        "Audit only public webpages. For a visual user result, call audit_website first, then pass its complete structuredContent unchanged to render_website_audit. Explain top priorities at the user's technical level. Never describe the result as a certification or ranking guarantee.",
    },
  );

  registerAppResource(
    server,
    "nymrel-website-audit-widget",
    WIDGET_URI,
    {},
    async () => ({
      contents: [
        {
          uri: WIDGET_URI,
          mimeType: RESOURCE_MIME_TYPE,
          text: widgetHtml,
          _meta: {
            ui: {
              prefersBorder: false,
              domain: "https://nymrel.com",
              csp: {
                connectDomains: [],
                resourceDomains: [],
              },
            },
            "openai/widgetDescription":
              "A warm, concise Nymrel report showing the website score, top priorities, and filterable technical findings.",
          },
        },
      ],
    }),
  );

  server.registerTool(
    "audit_website",
    {
      title: "Audit a public website",
      description:
        "Use when someone wants to check one public webpage for technical search, sharing, accessibility, structure, or AI-readability signals. Returns a point-in-time report as structured data. After success, pass the complete structuredContent unchanged to render_website_audit when the user should see the Nymrel report UI.",
      inputSchema: auditInputSchema,
      outputSchema: auditReportSchema.shape,
      annotations: {
        readOnlyHint: true,
        destructiveHint: false,
        openWorldHint: true,
        idempotentHint: true,
      },
      _meta: {
        "openai/toolInvocation/invoking": "Nymrel is checking the page…",
        "openai/toolInvocation/invoked": "Website audit ready.",
      },
    },
    async ({ url }) => {
      try {
        const report = await auditWebsite(url);
        return {
          structuredContent: report,
          content: [{ type: "text" as const, text: reportText(report) }],
        };
      } catch (error) {
        return errorResult(error);
      }
    },
  );

  registerAppTool(
    server,
    "render_website_audit",
    {
      title: "Show the Nymrel website audit",
      description:
        "Render the polished Nymrel report after audit_website succeeds. Always call audit_website first and pass its complete structuredContent to this tool unchanged. The report digest is verified before rendering.",
      inputSchema: auditReportSchema.shape,
      outputSchema: auditReportSchema.shape,
      annotations: {
        readOnlyHint: true,
        destructiveHint: false,
        openWorldHint: false,
        idempotentHint: true,
      },
      _meta: {
        ui: { resourceUri: WIDGET_URI },
        "openai/outputTemplate": WIDGET_URI,
        "openai/toolInvocation/invoking": "Preparing the Nymrel report…",
        "openai/toolInvocation/invoked": "Nymrel report shown.",
      },
    },
    async (input) => {
      const parsed = auditReportSchema.safeParse(input);
      if (!parsed.success || !verifyAuditReport(parsed.data)) {
        return {
          isError: true,
          content: [
            {
              type: "text" as const,
              text: "The audit report changed before rendering. Run audit_website again and pass its complete structuredContent unchanged.",
            },
          ],
        };
      }
      return {
        structuredContent: parsed.data,
        content: [{ type: "text" as const, text: reportText(parsed.data) }],
      };
    },
  );

  return server;
}

function setCors(res: ServerResponse): void {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Expose-Headers", "Mcp-Session-Id");
}

function json(res: ServerResponse, status: number, payload: unknown): void {
  res.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "cache-control": "no-store",
    "x-content-type-options": "nosniff",
  });
  res.end(JSON.stringify(payload));
}

function preview(res: ServerResponse): void {
  const bootstrap = JSON.stringify(previewReport).replace(/</g, "\\u003c");
  const html = widgetHtml.replace(
    "</head>",
    `<script>window.__NYMREL_PREVIEW__=${bootstrap};</script></head>`,
  );
  res.writeHead(200, {
    "content-type": "text/html; charset=utf-8",
    "cache-control": "no-store",
    "content-security-policy":
      "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:; font-src 'none'; connect-src 'none'; frame-ancestors 'self'",
    "referrer-policy": "no-referrer",
    "x-content-type-options": "nosniff",
    "x-frame-options": "SAMEORIGIN",
  });
  res.end(html);
}

async function handleHttp(req: IncomingMessage, res: ServerResponse): Promise<void> {
  if (!req.url) {
    json(res, 400, { error: "missing_url" });
    return;
  }
  const requestUrl = new URL(req.url, `http://${req.headers.host ?? "127.0.0.1"}`);

  if (req.method === "GET" && (requestUrl.pathname === "/" || requestUrl.pathname === "/healthz")) {
    json(res, 200, {
      name: "Nymrel Website Audit",
      version: VERSION,
      status: "ok",
      mcp: MCP_PATH,
      preview: "/preview",
    });
    return;
  }
  if (req.method === "GET" && requestUrl.pathname === "/preview") {
    preview(res);
    return;
  }
  if (req.method === "OPTIONS" && requestUrl.pathname === MCP_PATH) {
    res.writeHead(204, {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "POST, GET, DELETE, OPTIONS",
      "Access-Control-Allow-Headers":
        "content-type, accept, mcp-session-id, mcp-protocol-version, last-event-id",
      "Access-Control-Expose-Headers": "Mcp-Session-Id",
      "Access-Control-Max-Age": "86400",
    });
    res.end();
    return;
  }

  const mcpMethods = new Set(["POST", "GET", "DELETE"]);
  if (requestUrl.pathname === MCP_PATH && req.method && mcpMethods.has(req.method)) {
    setCors(res);
    const server = createNymrelMcpServer();
    const transport = new StreamableHTTPServerTransport({
      sessionIdGenerator: undefined,
      enableJsonResponse: true,
    });
    res.on("close", () => {
      void transport.close();
      void server.close();
    });
    try {
      await server.connect(transport);
      await transport.handleRequest(req, res);
    } catch (error) {
      console.error("Nymrel MCP request failed", error);
      if (!res.headersSent) json(res, 500, { error: "internal_server_error" });
    }
    return;
  }

  json(res, 404, { error: "not_found" });
}

export async function startHttpServer(port = Number(process.env.PORT ?? 8787)) {
  const httpServer = createServer((req, res) => {
    void handleHttp(req, res);
  });
  await new Promise<void>((resolve, reject) => {
    httpServer.once("error", reject);
    httpServer.listen(port, "127.0.0.1", resolve);
  });
  console.log(`Nymrel Website Audit MCP listening on http://127.0.0.1:${port}${MCP_PATH}`);
  return httpServer;
}

async function main(): Promise<void> {
  if (process.argv.includes("--stdio")) {
    const server = createNymrelMcpServer();
    const transport = new StdioServerTransport();
    await server.connect(transport);
    return;
  }
  await startHttpServer();
}

const isEntryPoint = process.argv[1]
  ? import.meta.url.toLowerCase() === pathToFileURL(process.argv[1]).href.toLowerCase()
  : false;

if (isEntryPoint) {
  main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
}
