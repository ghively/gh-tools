/**
 * Starter agent on the Claude Agent SDK (TypeScript).
 *
 * The shape to keep even after you replace every demo piece: a scoped tool
 * surface, custom tools as an in-process MCP server, a deterministic
 * PreToolUse floor, a cheap-model subagent for fan-out, and cost/session
 * capture on exit.
 */
import {
  query,
  tool,
  createSdkMcpServer,
  type Options,
} from "@anthropic-ai/claude-agent-sdk";
import { z } from "zod";
import { readFile } from "node:fs/promises";

const SYSTEM_PROMPT = `You are a repository analyst. Your job is to answer
questions about the current repository for its maintainer, read-only.

Never modify files. If a question requires changing something, describe the
change instead and say you are read-only. Cite file paths for every claim.`;

// --- 1. Custom tool: in-process MCP server (mcp__starter__word_count) ------
const wordCount = tool(
  "word_count",
  "Count lines/words in a file the built-in tools already read",
  { path: z.string() },
  async (args) => {
    let text: string;
    try {
      text = await readFile(args.path, "utf-8");
    } catch (err) {
      return { content: [{ type: "text", text: `error: ${String(err)}` }] };
    }
    const result = `${args.path}: ${text.split("\n").length} lines, ${
      text.split(/\s+/).filter(Boolean).length
    } words`;
    return { content: [{ type: "text", text: result }] };
  },
);

const starterTools = createSdkMcpServer({
  name: "starter",
  version: "1.0.0",
  tools: [wordCount],
});

// --- 2. Deterministic floor: the model cannot override this ----------------
const NEVER_RUN = ["rm -rf /", "curl", "wget", "mkfs", "dd if="];

async function denyNeverRun(input: Record<string, unknown>) {
  const command = String(
    (input["tool_input"] as Record<string, unknown> | undefined)?.["command"] ?? "",
  );
  for (const marker of NEVER_RUN) {
    if (command.includes(marker)) {
      return {
        hookSpecificOutput: {
          hookEventName: "PreToolUse" as const,
          permissionDecision: "deny" as const,
          permissionDecisionReason: `read-only analyst: '${marker}' is never allowed`,
        },
      };
    }
  }
  return {};
}

// --- 3. Options: the design decisions, in code ------------------------------
const options: Options = {
  systemPrompt: SYSTEM_PROMPT,
  // Stage-4 tool surface: read-only job => read-only tools + Bash for git
  // inspection, gated by the floor above.
  allowedTools: [
    "Read",
    "Glob",
    "Grep",
    "Bash",
    "mcp__starter__word_count",
    "Agent",
  ],
  mcpServers: { starter: starterTools },
  hooks: {
    PreToolUse: [{ matcher: "Bash", hooks: [denyNeverRun] }],
  },
  agents: {
    "file-summarizer": {
      description:
        "Summarizes a single file's purpose and structure. Use when many " +
        "files need summarizing in parallel.",
      prompt:
        "Summarize the given file: purpose, key symbols, surprises. " +
        "Five bullet points maximum.",
      tools: ["Read"],
      model: "haiku", // fan-out work goes to the cheap tier
    },
  },
  permissionMode: "default",
  maxTurns: 20,
  cwd: ".",
};

async function run(prompt: string): Promise<void> {
  for await (const message of query({ prompt, options })) {
    if (message.type === "result" && message.subtype === "success") {
      console.log(message.result);
      console.error(
        `\n[cost $${message.total_cost_usd.toFixed(4)} | session ${message.session_id}]`,
      );
    }
  }
}

const prompt = process.argv.slice(2).join(" ");
if (!prompt) {
  console.error('usage: npm start -- "<question about this repo>"');
  process.exit(2);
}
await run(prompt);
