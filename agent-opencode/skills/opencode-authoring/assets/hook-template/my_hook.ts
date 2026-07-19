import { appendFile, mkdir } from "node:fs/promises"
import { dirname } from "node:path"
import type { Plugin } from "@opencode-ai/plugin"

const auditLog = process.env.MY_AGENT_AUDIT_LOG ?? ""

async function logLine(line: string): Promise<void> {
  if (!auditLog) return
  try {
    await mkdir(dirname(auditLog), { recursive: true })
    await appendFile(auditLog, `${line}\n`)
  } catch {
    // safety logging is fail-open
  }
}

// (regex, reason) — matched case-insensitively against the flattened command.
// Every entry needs a test vector proving it blocks, and a benign neighbor
// proving it doesn't.
const blockPatterns: [RegExp, string][] = [
  [/REPLACE-with-a-never-run-primitive/i, "REPLACE: reason shown to the operator"],
]

const plugin: Plugin = async () => {
  return {
    "tool.execute.before": async (input, output) => {
      const args = (output.args ?? {}) as Record<string, unknown>
      let command = ""
      try {
        if (input.tool.toLowerCase() === "bash") {
          command = typeof args.command === "string" ? args.command : ""
        }
      } catch {
        await logLine(`${new Date().toISOString()}\tPARSE_ERROR_ALLOW`)
        return // fail open: a broken hook must never brick operations
      }
      if (!command) return

      const flat = command.replace(/\n/g, " ")
      for (const [pattern, reason] of blockPatterns) {
        if (pattern.test(flat) || pattern.test(command)) {
          await logLine(`${new Date().toISOString()}\tBLOCK\t${reason}\t${flat.slice(0, 300)}`)
          throw new Error(`safety floor: ${reason}`)
        }
      }
      await logLine(`${new Date().toISOString()}\tallow\t${flat.slice(0, 300)}`)
    },
  }
}

export default plugin
