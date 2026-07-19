import { appendFile, mkdir } from "node:fs/promises"
import { dirname, normalize, join } from "node:path"
import type { Plugin } from "@opencode-ai/plugin"

type Args = Record<string, unknown>
const home = process.env.HOME ?? ""
const safetyLog = process.env.AGENT_FOUNDRY_AUDIT_LOG ?? join(home, ".config/opencode/agent-foundry/safety-audit.log")
const toolAuditLog = process.env.AGENT_FOUNDRY_TOOL_AUDIT_LOG ?? join(home, ".config/opencode/agent-foundry/tool-audit.jsonl")

const BT = String.fromCharCode(96) // backtick, kept out of regex literals for parser safety
const blockPatterns: [RegExp, string][] = [
  [/(?:curl|wget|fetch)\b[^|]*\|\s*(?:sh|bash|zsh|python\d?|perl|ruby|node)\b/i, "remote fetch piped to an interpreter"],
  [/\|\s*(?:sh|bash)\b[^|]*\b(?:curl|wget)\b/i, "interpreter run after a remote fetch"],
  [/(?:base64|xxd)\b[^|]*(?:-d|--decode|-r)[^|]*\|\s*(?:sh|bash|python\d?)/i, "encoded payload decoded into an interpreter"],
  [/echo\s+[^|]*\|\s*(?:base64|xxd)\b[^|]*\|\s*(?:sh|bash)/i, "encoded payload piped to an interpreter"],
  [new RegExp("(?:curl|wget|fetch)\\b[^;&|\\n" + BT + "]*?\\s-{1,2}o(?:utput)?[=\\s]+['\"]?([^\\s'\";&|" + BT + "]+)[^;&|\\n]*[;&|\\n]+[^\\n]*?\\b(?:sh|bash|zsh|python\\d?|perl|ruby|node)\\s+['\"]?\\1(?=['\"\\s;&|]|$)", "i"), "remote download then execution of the downloaded file"],
  [new RegExp("\\beval\\b\\s*['\"]?[" + BT + "$]\\(?[^\\n]*?\\b(?:curl|wget|fetch)\\b", "i"), "eval of a remote-fetch command substitution"],
  [new RegExp("\\b(?:sh|bash|zsh|python\\d?|perl|ruby|node)\\s+-c\\b[^\\n]*?[" + BT + "$]\\(?[^\\n]*?\\b(?:curl|wget|fetch)\\b", "i"), "interpreter -c running a remote-fetch command substitution"],
  [new RegExp("(?:^|[\\n;&|])\\s*(?:\\$\\(|" + BT + ")\\s*(?:sudo\\s+|env\\s+\\S+=\\S+\\s+)*(?:curl|wget|fetch)\\b", "i"), "bare command substitution executing a remote fetch"],
  [/\bdd\b[^|]*\bof=\/dev\/(?:sd|nvme|vd|hd|xvd)/i, "dd writing to a block device"],
  [/\bmkfs\.\w+\b/i, "mkfs (filesystem destroy)"],
  [/>\s*\/dev\/(?:sd|nvme|vd|hd|xvd)/i, "redirect to a block device"],
  [/\bshred\b[^|]*\/dev\//i, "shred on a device"],
  [/\brm\s+(?:-\w*r\w*\s+)+\/(?:\s|$|;|&|\*|['"])/i, "rm -rf at filesystem root"],
  [/\brm\b[^|]*--no-preserve-root/i, "rm --no-preserve-root"],
  [/:\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}/i, "fork bomb"],
  [/docker\s+run\b[^|]*(?:--privileged|-v\s+\/(?:[:\s]|$)|--pid=host|--network=host|--ipc=host|--userns=host)/i, "docker run with host-root escape flags"],
  [/docker\s+run\b[^|\n]*--cap-add[=\s]+(?:cap_)?(?:sys_admin|sys_module|sys_ptrace|sys_rawio|sys_boot|dac_read_search|dac_override|bpf|all)\b/i, "docker run adding an escape-enabling Linux capability"],
  [/nsenter\b[^|]*--target\s+1\b/i, "nsenter into PID 1 (host escape)"],
  [/\bunshare\b[^|]*--pid\s+/i, "unshare into a new PID namespace"],
  [/(?:useradd|adduser|usermod|passwd|chpasswd)\b/i, "account creation or password change"],
  [/(?:iptables\s+-F|ip6tables\s+-F|ufw\s+disable|nft\s+flush\s+ruleset|firewall-cmd\s+--remove)/i, "firewall flush / disable"],
  [/(?:shutdown|reboot|poweroff|halt)\b/i, "host power-state change"],
  [/>\s*\/etc\/(?:sudoers|passwd|shadow|group|crontab)\b/i, "overwrite a critical identity/system file"],
  [/tee\s+(?:-a\s+)?\/etc\/(?:sudoers|passwd|shadow|group|crontab)\b/i, "write a critical identity/system file via tee"],
  [/>\s*~?\/\.ssh\/(?:authorized_keys|id_|config)\b/i, "write SSH keys/config (backdoor)"],
  [/\bcrontab\b\s+(?:-u\s+\S+\s+)?(?:-[er]\b|-(?=\s|$)|[^\s-]\S*)/i, "crontab install/edit/remove (persistence)"],
  [/chmod\s+[0-7]{3,4}\s+\/(?:etc|boot|root|usr)(?:\/|$)/i, "world-writable on a system directory"],
  [/git\s+config\b[^|]*core\.sshCommand/i, "git sshCommand tampering"]
]

const protectedRoots = ["/etc/sudoers", "/etc/sudoers.d", "/etc/passwd", "/etc/shadow", "/etc/group", "/etc/gshadow", "/boot", "/proc", "/sys", "/etc/cron.d", "/etc/cron.daily", "/etc/cron.hourly", "/etc/cron.weekly", "/etc/cron.monthly", "/etc/systemd/system", join(home, ".ssh")]
const secretPatterns: [RegExp, string][] = [
  [/-----BEGIN [A-Z ]+ PRIVATE KEY-----/i, "private key"],
  [/\bAKIA[0-9A-Z]{16}\b/, "AWS access key ID"],
  [/\bgh[pousr]_[A-Za-z0-9]{20,}\b/, "GitHub token"],
  [/\bgithub_pat_[A-Za-z0-9_]{20,}\b/, "GitHub fine-grained token"],
  [/\bxox[baprs]-[0-9-]{10,}-[0-9A-Za-z-]{10,}\b/, "Slack token"],
  [/\bsk-[A-Za-z0-9]{20,}\b/, "API key"],
  [/\bAIza[A-Za-z0-9_-]{35}\b/, "Google API key"],
  [/\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b/, "JWT token"],
  [/postgres(?:ql)?:\/\/[^\s:]+:[^\s@]+@/i, "PostgreSQL URL with password"]
]
const placeholder = /example|sample|placeholder|redacted|changeme|your[_-]|xxxx|\.\.\.|\$\{|<redacted>/i

export function isDestructiveCommand(command: unknown): string | null {
  if (typeof command !== "string") return null
  try {
    const flat = command.replace(/\n/g, " ")
    for (const [pattern, reason] of blockPatterns) if (pattern.test(flat) || pattern.test(command)) return reason
    return null
  } catch {
    return null
  }
}

export function normalizePath(value: unknown, cwd: string = process.cwd()): string {
  if (typeof value !== "string") return ""
  try {
    const expanded = value.startsWith("~") ? join(home, value.slice(1)) : value
    return normalize(expanded.startsWith("/") ? expanded : join(cwd, expanded))
  } catch {
    return ""
  }
}

export function isProtectedPath(value: unknown, cwd: string = process.cwd()): boolean {
  if (typeof value !== "string") return false
  try {
    const candidate = normalizePath(value, cwd)
    return protectedRoots.some(root => candidate === normalizePath(root) || candidate.startsWith(`${normalizePath(root)}\/`))
  } catch {
    return false
  }
}

function patchPaths(text: string): string[] {
  return [...text.matchAll(/^\*\*\* (?:Add|Update|Delete) File:\s*(.+)$/gm), ...text.matchAll(/^\*\*\* Move to:\s*(.+)$/gm)].map(match => match[1].trim())
}

export function secretReason(content: unknown): string | null {
  if (typeof content !== "string") return null
  try {
    for (const [pattern, reason] of secretPatterns) {
      const match = pattern.exec(content)
      if (match && !placeholder.test(content.slice(Math.max(0, match.index - 40), match.index + match[0].length + 40))) return reason
    }
    return null
  } catch {
    return null
  }
}

async function logLine(file: string, line: string): Promise<void> {
  try { await mkdir(dirname(file), { recursive: true }); await appendFile(file, `${line}\n`) } catch { /* safety logging is fail-open */ }
}

const plugin: Plugin = async (input, options) => {
  const client = input?.client
  const secretCheck = Boolean(options?.enableSecretCheck)
  const auditTrail = Boolean(options?.enableAuditTrail)
  return {
    "tool.execute.before": async (input, output) => {
      try {
        const tool = typeof input?.tool === "string" ? input.tool.toLowerCase() : ""
        const rawArgs = output?.args
        const args = (rawArgs && typeof rawArgs === "object" ? rawArgs : {}) as Args
        let reason: string | null = null
        if (tool === "bash") reason = isDestructiveCommand(args?.command)
        if ((tool === "write" || tool === "edit") && typeof args?.filePath === "string" && isProtectedPath(args.filePath)) reason = `privileged write to ${normalizePath(args.filePath)}`
        if (tool === "apply_patch" && typeof args?.patchText === "string" && patchPaths(args.patchText).some(value => isProtectedPath(value))) reason = "privileged write in apply_patch"
        if (reason) { await logLine(safetyLog, `${new Date().toISOString()}\tBLOCK\t${tool}\t${reason}`); throw new Error(`safety floor: ${reason}`) }
        if (secretCheck && tool === "write" && typeof args?.content === "string") reason = secretReason(args.content)
        if (secretCheck && tool === "edit" && typeof args?.newString === "string") reason = secretReason(args.newString)
        if (reason) { await logLine(safetyLog, `${new Date().toISOString()}\tBLOCK_SECRET\t${tool}\t${reason}`); throw new Error(`safety floor: detected ${reason}`) }
        if (tool === "bash" && typeof args?.command === "string") await logLine(safetyLog, `${new Date().toISOString()}\tallow\tbash\t${args.command.slice(0, 300)}`)
      } catch (e) {
        if (e instanceof Error && e.message.startsWith("safety floor: ")) throw e
      }
    },
    "tool.execute.after": async (input, output) => {
      if (!auditTrail) return
      try {
        const entry = { ts: new Date().toISOString(), session_id: String(input?.sessionID ?? "").slice(0, 64), tool: String(input?.tool ?? ""), args: input?.args }
        await logLine(toolAuditLog, JSON.stringify(entry).slice(0, 1200))
        if (client?.app?.log) await client.app.log({ body: { service: "agent-foundry-safety", level: "info", message: `Tool execution: ${input.tool}`, extra: entry } })
      } catch { /* audit is fail-open */ }
    }
  }
}

export default plugin
