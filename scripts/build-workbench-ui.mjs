import { readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { build } from "esbuild";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const templatePath = path.join(root, "ui", "workbench.html");
const entryPath = path.join(root, "ui", "workbench.js");
const outputPath = path.join(root, "hosted-mcp", "api", "assets", "workbench.html");
const checkOnly = process.argv.slice(2).includes("--check");
const normalizeEol = (value) => value.replace(/\r\n?/g, "\n");
const template = normalizeEol(await readFile(templatePath, "utf8"));
const marker = "    // WORKBENCH_BUNDLE";
if (!template.includes(marker) || template.indexOf(marker) !== template.lastIndexOf(marker)) {
  throw new Error("workbench.html must contain exactly one WORKBENCH_BUNDLE marker");
}

const built = await build({
  entryPoints: [entryPath],
  bundle: true,
  write: false,
  platform: "browser",
  format: "iife",
  target: ["es2022"],
  // Preserve multiline SDK strings as escaped strings in the generated asset.
  supported: { "template-literal": false },
  minify: true,
  legalComments: "none",
  charset: "utf8",
  metafile: true,
  logLevel: "silent",
});

function packageFromInput(input) {
  const normalized = input.replaceAll("\\", "/");
  const marker = "node_modules/";
  const offset = normalized.lastIndexOf(marker);
  if (offset < 0) return null;
  const parts = normalized.slice(offset + marker.length).split("/");
  if (!parts[0] || parts[0].startsWith(".")) return null;
  const packageParts = parts[0].startsWith("@") ? parts.slice(0, 2) : parts.slice(0, 1);
  if (packageParts.some((part) => !part)) throw new Error(`Cannot identify package root for bundled input: ${input}`);
  return packageParts.join("/");
}

async function licenseNotices(inputs) {
  const packageNames = [...new Set(inputs.map(packageFromInput).filter(Boolean))].sort((a, b) => a.localeCompare(b));
  const notices = [];
  for (const name of packageNames) {
    const packageRoot = path.join(root, "node_modules", ...name.split("/"));
    const metadataPath = path.join(packageRoot, "package.json");
    let metadata;
    try {
      metadata = JSON.parse(await readFile(metadataPath, "utf8"));
    } catch {
      throw new Error(`Bundled package metadata is unavailable: ${name}`);
    }
    const declared = typeof metadata.license === "string"
      ? metadata.license
      : Array.isArray(metadata.licenses)
        ? metadata.licenses.map((entry) => entry?.type).filter(Boolean).join(" OR ")
        : metadata.license?.type;
    if (typeof declared !== "string" || !declared.trim()) {
      throw new Error(`Bundled package has no usable license declaration: ${name}`);
    }
    const candidates = [metadata.license?.file, "LICENSE", "LICENSE.md", "LICENSE.txt", "LICENCE", "COPYING"]
      .filter((value) => typeof value === "string" && value.trim());
    let text;
    let licenseFile;
    for (const candidate of candidates) {
      try {
        text = await readFile(path.join(packageRoot, candidate), "utf8");
        licenseFile = candidate;
        break;
      } catch { /* try the next conventional license filename */ }
    }
    if (typeof text !== "string" || text.trim().length < 100) {
      throw new Error(`Bundled package has no usable full license text: ${name}`);
    }
    const cleanText = text.replace(/\r\n?/g, "\n").trim().replace(/\*\//g, "* /");
    notices.push(`/*!\n * Third-party license: ${metadata.name} ${metadata.version} (${declared})\n * License file: node_modules/${name}/${licenseFile}\n *\n${cleanText.split("\n").map((line) => line.trimEnd() ? ` * ${line.trimEnd()}` : " *").join("\n")}\n */`);
  }
  if (!notices.length) throw new Error("The workbench bundle has no package license notices");
  return notices.join("\n\n");
}

const thirdPartyNotices = await licenseNotices(Object.keys(built.metafile.inputs));
const rawBundle = `${thirdPartyNotices}\n\n${built.outputFiles[0].text}`;
const bundle = rawBundle.replace(/<\/script/gi, "<\\/script");
// Use a callback so dollar sequences inside the generated JavaScript are not
// interpreted as String.replace substitution tokens.
const expected = template.replace(marker, () => bundle);

if (checkOnly) {
  let actual;
  try {
    actual = normalizeEol(await readFile(outputPath, "utf8"));
  } catch {
    throw new Error("Generated workbench asset is missing; run node scripts/build-workbench-ui.mjs");
  }
  if (actual !== expected) throw new Error("Generated workbench asset is stale; run node scripts/build-workbench-ui.mjs");
  process.stdout.write("workbench asset is current\n");
} else {
  await writeFile(outputPath, expected, "utf8");
  process.stdout.write(`built ${path.relative(root, outputPath)}\n`);
}
