#!/usr/bin/env python3
"""Starter agent on the Claude Agent SDK.

The shape to keep even after you replace every demo piece: a scoped tool
surface, custom tools as an in-process MCP server, a deterministic PreToolUse
floor, a cheap-model subagent for fan-out, and cost/session capture on exit.
"""
import asyncio
import sys

from claude_agent_sdk import (
    AgentDefinition,
    ClaudeAgentOptions,
    HookMatcher,
    ResultMessage,
    create_sdk_mcp_server,
    query,
    tool,
)

SYSTEM_PROMPT = """\
You are a repository analyst. Your job is to answer questions about the
current repository for its maintainer, read-only.

Never modify files. If a question requires changing something, describe the
change instead and say you are read-only. Cite file paths for every claim.
"""


# --- 1. Custom tool: in-process MCP server (name: mcp__starter__word_count) --
@tool("word_count", "Count lines/words in a file the built-in tools already read",
      {"path": str})
async def word_count(args):
    try:
        with open(args["path"], encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        result = f"{args['path']}: {len(text.splitlines())} lines, {len(text.split())} words"
    except OSError as exc:
        result = f"error: {exc}"
    return {"content": [{"type": "text", "text": result}]}


starter_tools = create_sdk_mcp_server(
    name="starter", version="1.0.0", tools=[word_count])


# --- 2. Deterministic floor: the model cannot override this ------------------
NEVER_RUN = ("rm -rf /", "curl", "wget", "mkfs", "dd if=")


async def deny_never_run(input_data, tool_use_id, context):
    command = str((input_data.get("tool_input") or {}).get("command", ""))
    for marker in NEVER_RUN:
        if marker in command:
            return {"hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason":
                    f"read-only analyst: '{marker}' is never allowed",
            }}
    return {}


# --- 3. Options: the design decisions, in code -------------------------------
def build_options() -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT,
        # Stage-4 tool surface: read-only job => read-only tools + Bash for
        # git inspection, gated by the floor above.
        allowed_tools=["Read", "Glob", "Grep", "Bash",
                       "mcp__starter__word_count", "Agent"],
        mcp_servers={"starter": starter_tools},
        hooks={"PreToolUse": [HookMatcher(matcher="Bash",
                                          hooks=[deny_never_run])]},
        agents={
            "file-summarizer": AgentDefinition(
                description="Summarizes a single file's purpose and structure. "
                            "Use when many files need summarizing in parallel.",
                prompt="Summarize the given file: purpose, key symbols, "
                       "surprises. Five bullet points maximum.",
                tools=["Read"],
                model="haiku",  # fan-out work goes to the cheap tier
            ),
        },
        permission_mode="default",
        max_turns=20,
        cwd=".",
    )


async def run(prompt: str) -> None:
    async for message in query(prompt=prompt, options=build_options()):
        if isinstance(message, ResultMessage):
            print(message.result)
            print(f"\n[cost ${message.total_cost_usd:.4f} | "
                  f"session {message.session_id}]", file=sys.stderr)


def cli() -> None:
    if len(sys.argv) < 2:
        print("usage: python src/agent.py \"<question about this repo>\"",
              file=sys.stderr)
        raise SystemExit(2)
    asyncio.run(run(" ".join(sys.argv[1:])))


if __name__ == "__main__":
    cli()
