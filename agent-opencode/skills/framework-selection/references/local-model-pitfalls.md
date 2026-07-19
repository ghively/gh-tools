# Local-Model Agent Pitfalls — Hard-Won Lessons

Lessons from building a production LangGraph agent (60+ tools wrapping REST APIs and CLI
providers) against a local Ollama endpoint on a consumer GPU (e.g., a 12 GB RTX 3060-class
card). Every lesson below generalizes to any framework pointed at a local model; the code
snippets use LangChain/LangGraph because that's where they were discovered.

The meta-lesson: **most "agent bugs" on local models are model-class or client-config bugs,
not code bugs.** Check the model and the client wiring before touching agent logic.

## 1. Thinking/reasoning models break streaming ReAct tool parsing

**Never use a "thinking" model (Qwen 3.x, DeepSeek-R1, o1-style reasoners) for a streaming
ReAct agent.** Thinking models emit reasoning tokens before the tool call. In streaming
mode those arrive as dozens of empty content chunks, and the tool call lands in the final
chunk — which some streaming parsers (observed with `ChatOllama`) never capture. The tool
never fires through the streaming path and the UI shows "No response."

The failure is **silent and intermittent**: simple queries ("hello") work because there's
no thinking phase; only tool-triggering queries break. It looks exactly like a frontend or
SSE bug. It is a model-selection bug.

Diagnosis: check the model card / `ollama show <model>` for a `thinking` capability. If
present, that model is a red flag for streaming tool use.

## 2. Model-selection decision table for agent workloads

(Model choice in depth is the `model-selection` skill; this table is the local-agent slice.)

| Use case | Model class | Example |
|---|---|---|
| Streaming ReAct agent (chat UI) | **Non-thinking, tool-capable** | `qwen2.5:7b`, `llama3.1:8b` |
| Batch/CLI agent (no streaming) | Thinking OK if tool support verified | newer reasoning models |
| Embedding / extraction | Dedicated embedding model | `mxbai-embed-large` |
| Complex reasoning, no tools | Thinking model, non-streaming | reasoning-tuned models |

Selection criteria for a tool-calling agent on a ~12 GB card:

1. **NOT a thinking/reasoning model** (see pitfall 1).
2. **Verified `tools` capability** — check, don't assume.
3. **7B–14B range** for a 12 GB GPU sharing VRAM with other services. The LLM earns its
   cost at intent parsing and exception handling, not deep reasoning — lighter is fine.
4. **Prefer proven, boring models.** Qwen 2.5, Llama 3.1, Mistral have well-tested
   tool-call formats in every framework. Bleeding-edge models bring bleeding-edge
   integration bugs.

If no off-the-shelf local model clears your tool-call bar (see pitfalls 1 and 6), the
escalation is a PEFT/LoRA fine-tune of a boring base model on your own tool-call
transcripts — a serving/training concern, not a framework one. That path (adapters,
data prep, VRAM budgets) is outside agent-foundry's scope; consult current
PEFT/LoRA documentation for the framework and model you are adapting.
try the config fixes in this file first, since most "the model can't tool-call" failures
are client wiring, not weights.

Verify BEFORE building anything on top — both query types must work:

```python
llm = ChatOllama(model="<candidate>", temperature=0).bind_tools(all_tools)
# 1. Simple query must stream text chunks with content.
# 2. Tool query through the agent loop must emit an on_tool_start event
#    AND stream a final grounded answer.
```

## 3. temperature=0 for tool calling

Non-zero temperature makes tool-call generation flaky on small local models: malformed
JSON args, wrong tool picked, free-text instead of a structured call. Set `temperature=0`
for any tool-routing agent (for providers that still honor it — current Anthropic models
reject `temperature` with a 400; see the `deterministic-agents` skill); save creative
temperatures for pure-prose nodes.

Corollary: **verify the temperature actually reaches the client.** Factory functions
(`create_llm()`) that hardcode `temperature=0` — or forget to pass the config value
through the constructor chain — silently ignore your settings file. Grep the chain.

## 4. The `num_ctx=2048` trap (context too small for tool schemas)

`ChatOllama` (and the `ollama` CLI) default to a 2048-token context. A ReAct agent with
30–70 tools spends 1,500–2,000 tokens on tool schemas alone — leaving no room for the
system prompt or user message. The symptom is subtle: the model *sometimes* calls tools,
*sometimes* outputs the tool call as JSON text, because when context is tight it falls
back to describing calls instead of making them.

Fix: pass `num_ctx=8192` (or higher) explicitly. 8192 is safe on a 12 GB card; go higher
on machines with more memory. The rule: context must comfortably exceed what the tool
schemas consume. 2048 is never enough for a production agent.

```python
llm = ChatOllama(base_url=..., model="qwen2.5:7b", temperature=0, num_ctx=8192)
```

## 5. Bind tools explicitly — auto-bind can silently fail

Prebuilt agent constructors are supposed to bind tools to the model internally, but with
some framework/client version pairs this silently fails: the model enters the loop with no
tool definitions and outputs JSON text of what it *would* call. Always bind explicitly:

```python
bound = llm.bind_tools(all_tools)          # explicit
agent = create_agent(bound, tools=all_tools, ...)  # constructor sees they match
```

## 6. Tool names in the system prompt → hallucinated JSON (small-model quirk)

When the system prompt names tools explicitly ("call get_queue immediately"), small local
models (observed aggressively on Qwen 2.5 7B) **output the tool call as a JSON code block
in the response text** instead of emitting a real tool call — the prompt text triggers
their fine-tuned "emit tool-call JSON" behavior.

Fix: **zero tool names in the system prompt.** Describe capabilities in natural language
("search the catalog", "check the queue"); let tool docstrings/schemas carry the contract
— the model discovers tools from the bound definitions, not prompt text. Also strip every
technical identifier (internal IDs, endpoint names, HTTP codes). And state the anti-JSON
rule as an absolute first rule ("ZERO JSON, ever") — small models take absolutes
literally and qualified rules ("try not to…") as optional.

Verification: run a search-type query; any `{` or `[` in the response text (not from tool
output) means the prompt still has a trigger somewhere.

## 7. Sync-vs-async middleware wrappers (`@wrap_model_call`)

LangChain v1's `create_agent` middleware decorator `@wrap_model_call` supports async — but
**only when the decorated function is `async def`**. A sync `def` under the decorator
raises at stream time:

> `NotImplementedError: Asynchronous implementation of awrap_model_call is not available.`

```python
# BROKEN — sync def under @wrap_model_call in an async/streaming agent
@wrap_model_call
def _trim_history(request, handler):
    return handler(request.override(...))

# WORKS
@wrap_model_call
async def _trim_history(request, handler):
    return await handler(request.override(...))
```

General rule for every framework: if the serving path is async/streaming (it almost always
is), define every middleware/hook/tool as `async def` and `await` the handler. The
sync-path test passing tells you nothing about the streaming path.

## 8. Circuit-breaker LLM client (local-first, cloud fallback)

Local endpoints fail differently from cloud APIs: the model gets evicted from VRAM,
another process OOMs the GPU, first-token latency after cold load is 15–30 s. A naive
client turns each of these into a hung request or a cascade of retries that queue up
behind a dead endpoint.

Wrap the local client in a circuit breaker:

```python
class ResilientLLM:
    def __init__(self, local, fallback=None, threshold=3, cooldown=60):
        self.local, self.fallback = local, fallback
        self.failures, self.open_until = 0, 0.0
        self.threshold, self.cooldown = threshold, cooldown

    async def ainvoke(self, *a, **kw):
        if time.monotonic() < self.open_until and self.fallback:
            return await self.fallback.ainvoke(*a, **kw)   # circuit open
        try:
            out = await self.local.ainvoke(*a, **kw)
            self.failures = 0                              # close on success
            return out
        except (httpx.ConnectError, httpx.ReadTimeout):
            self.failures += 1
            if self.failures >= self.threshold:
                self.open_until = time.monotonic() + self.cooldown
            if self.fallback:
                return await self.fallback.ainvoke(*a, **kw)
            raise
```

Rules of thumb: count only connection/timeout errors (a 400 is your bug, not an outage);
after the cooldown, let one probe request through (half-open) before fully closing; log
every open/close transition — silent fallback to a paid cloud model is a billing surprise.
Expect slow first tokens after cold start and set timeouts accordingly; SSE streaming
hides warmup because tokens appear as soon as generation starts.

## 9. Frontend: build vs reuse (default to reuse)

Before building ANY custom frontend for an agent, run this table. A real project burned
multiple sessions building and rebuilding a custom React dashboard the user rejected;
it was deleted and replaced with Open WebUI in 10 minutes — the backend had been correct
all along.

| Agent type | Frontend choice | Why |
|---|---|---|
| Chat-first agent (Q&A, tool calls, streaming) | **Open WebUI** (`open-webui/open-webui`) | Mobile, streaming, markdown, auth, theming free; connects to any OpenAI-compatible API; zero frontend code |
| Responses should render as **generated UI** (tables/charts/cards built from tool results) | **OpenUI** (`thesysdev/openui`) | Model emits a compact declarative UI language; frontend renders live components as they stream |
| Needs custom visual widgets no chat UI renders (live progress bars, artwork grids) | Custom React + Vite | Only when the UI *is* the product |
| Chat AND custom widgets | Open WebUI primary + widget page on the side | Ship value now, iterate visuals later |

**OpenUI ≠ Open WebUI** — completely different projects. Open WebUI is a self-hosted chat
frontend that displays the model's text as-is. OpenUI is a generative-UI framework where
the model's final answer is UI code. If a user says "generative UI" / "the interface
should be dynamic", that's OpenUI. Confusing them wastes a full deployment cycle.

Wiring pattern for either: expose the agent behind an OpenAI-compatible
`/v1/chat/completions` endpoint and point the frontend at it — the frontend layer stays a
thin proxy with no tool handling. Even when a custom frontend is justified, stand up Open
WebUI first and ship; add the custom page as a side project.

## 10. Serve strings to the LLM, structs to the frontend

Tools should return human-readable strings (the LLM sees them as text); dashboards need
raw numbers. Never call `@tool`-decorated functions from UI endpoints — they return
LLM-formatted prose (and in LangChain, Tool objects, not callables). Give each service a
client class (`_get`/`_post`) and build two thin layers over it: `@tool` wrappers that
format for the model, and JSON endpoints that return dicts for the UI. Related: don't
strip rich API fields (progress, size, ETA) out of tool output — enriched status strings
are what make the agent's reports useful.

## 11. Documentation drift — verify docs against runtime

Docs go stale silently: a README claiming "49 tools" when the registry loads 66, a
CLAUDE.md naming the wrong model. Worse, **subagent-produced documentation drifts by
construction**: a subagent documenting tools from source files will find functions that
exist in the codebase but were never imported into the runtime registry, and report the
larger number.

Always diff docs against the *running* system:

```bash
# Count tools documented in the reference
grep -c '^### `' docs/tool-reference.md

# Count tools actually registered at runtime
docker exec <container> python3 -c "from src.tools.registry import all_tools; print(len(all_tools))"

# Diff names to find the discrepancy
diff <(grep -oP '(?<=^### `)[a-z_]+' docs/tool-reference.md | sort) \
     <(docker exec <container> python3 -c "[print(t.name) for t in sorted(all_tools, key=lambda x: x.name)]" | sort)
```

Unregistered-but-documented functions go in an explicit "unregistered source functions"
section, never the headline count. Re-run the check after every tool add/remove or model
change, across README, agent-instructions file (CLAUDE.md), and tool reference.

## 12. The multi-turn verification test (do this before declaring the agent working)

A single-message test misses the two most common local-agent bugs at once — missing
conversation memory and hallucinated-JSON tool calls:

```bash
# Turn 1: a query that must trigger a real tool call, not a JSON code block
curl -s -X POST $AGENT/chat -d '{"message":"search for X"}'
# Turn 2: a follow-up that only works if turn 1's results are remembered
curl -s -X POST $AGENT/chat -d '{"message":"add the first one"}'
# "I don't know what you mean" → checkpointer missing or thread_id not passed
```

If the serving layer invokes the agent through two code paths (e.g., blocking invoke and
streaming events), the thread/session config must be passed on **both** — forgetting one
silently breaks memory on that path only.
