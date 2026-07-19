#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";

const input = process.env.OPENAPI_FILE || process.argv[2];
const output = process.env.TOOLS_FILE || process.argv[3] || "tools.json";

if (!input) {
  console.error("Usage: OPENAPI_FILE=openapi.json TOOLS_FILE=tools.json node scripts/generate-tools.mjs");
  process.exit(2);
}

const spec = JSON.parse(fs.readFileSync(input, "utf8"));
const tools = [];
const methods = new Set(["get", "post", "put", "patch", "delete"]);

function slug(value) {
  return String(value)
    .replace(/\{([^}]+)\}/g, "by_$1")
    .replace(/[^a-zA-Z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .toLowerCase()
    .slice(0, 80);
}

for (const [pathTemplate, item] of Object.entries(spec.paths || {})) {
  for (const [method, op] of Object.entries(item || {})) {
    if (!methods.has(method)) continue;
    const operationId = op.operationId || `${method}_${slug(pathTemplate)}`;
    const summary = op.summary || op.description || `${method.toUpperCase()} ${pathTemplate}`;
    tools.push({
      name: slug(operationId),
      description: String(summary).replace(/\s+/g, " ").trim(),
      method: method.toUpperCase(),
      pathTemplate,
      guarded: method !== "get"
    });
  }
}

fs.writeFileSync(path.resolve(output), JSON.stringify({ tools }, null, 2) + "\n");
console.error(`Wrote ${tools.length} tools to ${output}`);
