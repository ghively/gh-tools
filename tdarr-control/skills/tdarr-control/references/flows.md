# Tdarr 2.x flows — the visual node-graph workflow system

Tdarr 2.x introduced **flows** as the successor to the 1.x plugin stack. A flow
is a directed graph of nodes; each node does one thing (filter, transcode,
remux, clean audio, etc.). The same nodes can be combined visually in the UI
or as code.

## Plugin stacks vs flows — when to use which

| | 1.x plugin stack | 2.x flow |
|---|---|---|
| **Mental model** | Linear list of plugins | Directed graph of nodes |
| **Control flow** | Sequential; `break` to stop | Branch + loop; explicit edges |
| **Reusability** | One library = one stack | One flow can serve multiple libraries |
| **Visibility** | Plain text logs | Visual node-graph (easier to debug) |
| **Community support** | 107 plugins in catalog | Growing; uses the same `00td_filter_*` library |
| **Power** | Lower | Higher (conditionals, parallel branches) |
| **Maturity** | Battle-tested | Newer; some rough edges |

**Recommendation:** for a new Tdarr deployment, **start with flows**. They're
the future. Use plugin stacks only when a specific community plugin doesn't
have a flow equivalent yet.

Both can coexist; each library picks one or the other.

## Flow node types

The flow node catalog (searchable via `tdarr_search_flow_plugins(string="",
plugin_type="flow")`):

### Filter nodes (gate the flow)

These decide whether the file continues or breaks out of the flow.

| Node | Purpose |
|---|---|
| `filter_by_codec` | Continue only if video codec matches. |
| `filter_by_resolution` | Continue only if resolution matches. |
| `filter_by_size` | Continue only if file size is in range. |
| `filter_by_bitrate` | Continue only if bitrate is in range. |
| `filter_bit_depth` | Continue only if bit depth matches. |
| `filter_by_codec_tag_string` | Continue based on codec tag. |
| `filter_by_file_property` | Generic file-property filter. |
| `filter_by_stream_tag` | Continue based on stream tags. |
| `filter_modified_date` | Continue based on mtime. |
| `filter_break_stack_if_processed` | Control-flow: break out if a previous node processed the file. |

### Action nodes (modify the file)

| Node | Purpose |
|---|---|
| `action_transcode` | Run a transcode (ffmpeg/HandBrake). |
| `action_remux_container` | Change container without re-encoding. |
| `action_add_audio_stream_codec` | Add an audio stream. |
| `action_remove_stream_by_specified_property` | Remove streams by property. |
| `action_remove_audio_by_channel_count` | Remove audio by channel count. |
| `action_keep_one_audio_stream` | Keep only one audio track. |
| `action_standardise_audio_stream_codecs` | Standardize audio codecs. |
| `action_re_order_all_streams_v2` | Reorder streams. |
| `action_handbrake_basic_options` | HandBrake transcode. |
| `action_handbrake_ffmpeg_custom` | Custom HandBrake/ffmpeg. |

### Flow templates (pre-built flows)

Searchable via `tdarr_search_flow_templates(string="", plugin_type="flow")`.
Templates are pre-wired flows you can install and tweak. Common templates:

- **"HEVC Standardize"** — equivalent to plugin stack 1 in `workflows.md`.
- **"Compatibility MP4"** — equivalent to workflow 2.
- **"Audio normalization"** — equivalent to workflow 3.
- **"Library cleanup"** — equivalent to workflow 4 (remux + clean).

Install a template via the UI's flow editor, or programmatically via
`tdarr_db(mode="insert", collection="FlowsJSONDB", obj={...}, confirm=True)`
once you know the flow JSON shape.

## Flow JSON shape

A flow is stored in `FlowsJSONDB` as a document like:

```json
{
  "_id": "<flow_id>",
  "name": "My HEVC Standardize Flow",
  "description": "Convert everything to HEVC, clean audio/subs.",
  "nodes": [
    { "id": "n1", "type": "filter_by_codec", "config": { "codec": "hevc", "invert": true } },
    { "id": "n2", "type": "action_transcode", "config": {
        "ffmpegOperation": "-c:v hevc_nvenc -preset p6 -tune hq -rc vbr -cq 21 -pix_fmt yuv420p10le -c:a copy -c:s copy"
    } },
    { "id": "n3", "type": "action_re_order_all_streams_v2" }
  ],
  "edges": [
    { "from": "n1", "to": "n2", "condition": "passed" },
    { "from": "n2", "to": "n3", "condition": "success" }
  ]
}
```

To inspect existing flows: `tdarr_db(mode="getAll", collection="FlowsJSONDB")`.

To create one programmatically (write — confirm-gated):
```python
tdarr_db(
    mode="insert",
    collection="FlowsJSONDB",
    doc_id="my-hevc-flow",
    obj={ ...flow JSON... },
    confirm=True
)
```

## Pattern: porting a plugin stack to a flow

Take Workflow 1 (Standardize-on-HEVC) from `workflows.md`:

**Plugin stack version:**
1. `00td_filter_by_codec` (skip HEVC)
2. `MC93_Migz1FFMPEG` (NVENC HEVC)
3. `MC93_Migz3CleanAudio`
4. `MC93_Migz4CleanSubs`
5. `MC93_Migz6OrderStreams`

**Flow equivalent:**
```
START
  ↓
filter_by_codec(hevc) ─── matches ───► END (no transcode)
  ↓ doesn't match
action_transcode(hevc_nvenc -cq 21)
  ↓ success
filter_by_codec(audio in [DTS, TrueHD]) ─── matches ───► action_remove_stream
  ↓                                                  ↓
action_re_order_all_streams                    action_re_order_all_streams
  ↓                                                  ↓
END ◄─────────────────────────────────────────────────┘
```

The flow version is more explicit about what happens after each step (vs the
implicit "fall through to next plugin" of the stack).

## Flow plugin system — TypeScript + templating

Flow plugins are written in **TypeScript** (compiled to JavaScript). The
source lives in `HaveAGitGat/Tdarr_Plugins/FlowPluginsTs/CommunityFlowPlugins/`,
categorized by purpose (audio, video, helpers, tools, etc.).

Each plugin receives an `args` object with the full file context.

### Variable templating

In any flow-plugin input field, you can template values from `args`:

| Template | Resolves to |
|---|---|
| `{{{args.inputFileObj._id}}}` | Current file path |
| `{{{args.inputFileObj.fileSize}}}` | File size in bytes |
| `{{{args.inputFileObj.mediaInfo.track.0.BitRate}}}` | First track's bitrate (array index starts at 0) |
| `{{{args.inputFileObj.mediaInfo.track.1.CodecID}}}` | Second track's codec ID |
| `{{{args.userVariables.global.<name>}}}` | A global variable (set on Tools tab) |
| `{{{args.userVariables.library.<name>}}}` | A per-library variable (set on Libraries tab) |

This is **huge** for DRY. One flow can:
- Use different CQ values per library (`{{{args.userVariables.library.cq}}}`).
- Send a webhook with the filename in the body (`Send Web Request` plugin).
- Decide based on stream count, codec, bitrate, etc.

### Global vs library variables

- **Global** (Tools tab): server-wide. Use for API keys, webhook URLs, "default" values.
- **Library** (Libraries tab → Library Variables): per-library. Use for
  per-library quality targets, language preferences, etc.

### Flow plugin categories

The flow plugin catalog (in `FlowPluginsTs/CommunityFlowPlugins/`) is
organized by directory. Categories include:

- `audio/` — audio-stream filters + actions (check bitrate, codec, channel
  count, add/remove/convert audio).
- `video/` — video-stream filters + actions (codec, resolution, bit depth,
  HDR detection, transcode).
- `containers/` — container filters + remux actions.
- `subtitles/` — subtitle filters + actions.
- `helpers/` — generic helpers (Send Web Request, Run Classic Plugin, etc.).
- `tools/` — `Worker Type` (route to mapped/unmapped/etc. tagged nodes),
  `Requeue` (loop back in the flow), `Tags` operations.

The `Worker Type` flow node is what enables **flow-based worker routing**:
set the node tag and only matching nodes pick up that step. Critical for
mixed-node fleets (GPU node vs CPU node, mapped vs unmapped, etc.).

## Live flow data on gh-nvidia

Currently (2026-07-20, fresh Tdarr deploy) there are **zero flows** in
`FlowsJSONDB` — you haven't built any yet. Once you create your first flow via
the UI, run `tdarr_db(mode="getAll", collection="FlowsJSONDB")` to inspect its
JSON shape and learn the structure for any future programmatic creation.

## See also
- `workflows.md` — the canonical transcode patterns (mostly written as plugin
  stacks but all are portable to flows).
- `plugins.md` — full plugin catalog; many filter/action plugins are also flow nodes.
