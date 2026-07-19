import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import fs from "node:fs";
import path from "node:path";
import { z } from "zod";
import { logRequest } from "./lib/logger.js";
import { qs } from "./lib/qs.js";
import { retry } from "./lib/retry.js";

const API_BASE = process.env.API_BASE || "";
const AUTH_MODE = (process.env.AUTH_MODE || "none").toLowerCase();
const AUTH_TOKEN = process.env.AUTH_TOKEN || "";
const AUTH_HEADER = process.env.AUTH_HEADER || "Authorization";
const AUTH_QUERY_KEY = process.env.AUTH_QUERY_KEY || "api_key";
const ALLOW_DESTRUCTIVE = process.env.ALLOW_DESTRUCTIVE === "true";

if (!API_BASE) {
  console.error("Missing API_BASE");
  process.exit(1);
}

function joinUrl(base: string, p: string): string {
  if (/^https?:\/\//i.test(p)) return p;
  return `${base.replace(/\/$/, "")}/${p.replace(/^\//, "")}`;
}

function applyAuth(rawUrl: string, headers: Record<string, string>): string {
  if (AUTH_MODE === "bearer") headers.Authorization = `Bearer ${AUTH_TOKEN}`;
  if (AUTH_MODE === "header") headers[AUTH_HEADER] = AUTH_TOKEN;
  if (AUTH_MODE === "basic") headers.Authorization = `Basic ${AUTH_TOKEN}`;
  if (AUTH_MODE === "query") {
    const url = new URL(rawUrl);
    url.searchParams.set(AUTH_QUERY_KEY, AUTH_TOKEN);
    return url.toString();
  }
  return rawUrl;
}

async function requestJson(tool: string, method: string, p: string, body?: unknown, extraHeaders?: Record<string, string>) {
  const headers: Record<string, string> = { "Content-Type": "application/json", ...(extraHeaders || {}) };
  const url = applyAuth(joinUrl(API_BASE, p), headers);
  const started = Date.now();
  const call = async () => {
    const res = await fetch(url, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
    if (!res.ok) {
      const err = new Error(`HTTP ${res.status}: ${(await res.text()).slice(0, 300)}`) as Error & { status?: number };
      err.status = res.status;
      throw err;
    }
    const text = await res.text();
    return text ? JSON.parse(text) : {};
  };
  try {
    const data = method === "GET" ? await retry(call) : await call();
    logRequest({ tool, method, url, status: 200, ms: Date.now() - started });
    return { data, url };
  } catch (err) {
    const status = (err as Error & { status?: number }).status;
    logRequest({ tool, method, url, status: status ?? 0, ms: Date.now() - started });
    throw err;
  }
}

const server = new McpServer({ name: "any-api-mcp", version: "0.1.0" });
const headersSchema = z.record(z.string(), z.string()).optional();

server.tool("api_probe", "Safely probe an API path (read-only methods only).", { path: z.string(), method: z.enum(["GET", "HEAD", "OPTIONS"]).default("GET"), headers: headersSchema }, async (input) => {
  const { data, url } = await requestJson("api_probe", input.method.toUpperCase(), input.path, undefined, input.headers);
  return { content: [{ type: "text", text: `Probe ${url}\n${JSON.stringify(data).slice(0, 2000)}` }] };
});

server.tool("api_get", "GET a path under API_BASE with optional query parameters.", { path: z.string(), query: z.record(z.unknown()).optional(), headers: headersSchema }, async (input) => {
  const { data, url } = await requestJson("api_get", "GET", `${input.path}${qs(input.query)}`, undefined, input.headers);
  return { content: [{ type: "resource", resource: { uri: url, mimeType: "application/json", text: JSON.stringify(data) } }] };
});

for (const method of ["POST", "PUT", "DELETE"] as const) {
  server.tool(`api_${method.toLowerCase()}`, `${method} a path under API_BASE. Guarded by ALLOW_DESTRUCTIVE.`, { path: z.string(), payload: z.unknown().optional(), headers: headersSchema }, async (input) => {
    if (!ALLOW_DESTRUCTIVE) return { content: [{ type: "text", text: `Destructive tools disabled. Set ALLOW_DESTRUCTIVE=true to enable ${method}.` }] };
    const { data, url } = await requestJson(`api_${method.toLowerCase()}`, method, input.path, input.payload, input.headers);
    return { content: [{ type: "resource", resource: { uri: url, mimeType: "application/json", text: JSON.stringify(data) } }] };
  });
}

const toolsFile = path.resolve(process.cwd(), process.env.TOOLS_FILE || "tools.json");
if (fs.existsSync(toolsFile)) {
  const cfg = JSON.parse(fs.readFileSync(toolsFile, "utf8"));
  for (const t of cfg.tools || []) {
    const method = String(t.method || "GET").toUpperCase();
    const guarded = Boolean(t.guarded ?? method !== "GET");
    server.tool(String(t.name), String(t.description || `${method} ${t.pathTemplate}`), { pathParams: z.record(z.string()).optional(), query: z.record(z.unknown()).optional(), payload: z.unknown().optional(), headers: headersSchema }, async (input) => {
      if (guarded && !ALLOW_DESTRUCTIVE) return { content: [{ type: "text", text: "Destructive tool disabled. Set ALLOW_DESTRUCTIVE=true to enable." }] };
      const compiled = String(t.pathTemplate).replace(/\{([^}]+)\}/g, (_: string, key: string) => encodeURIComponent(input.pathParams?.[key] || ""));
      const { data, url } = await requestJson(String(t.name), method, `${compiled}${method === "GET" ? qs(input.query) : ""}`, input.payload, input.headers);
      return { content: [{ type: "resource", resource: { uri: url, mimeType: "application/json", text: JSON.stringify(data) } }] };
    });
  }
}

await server.connect(new StdioServerTransport());
