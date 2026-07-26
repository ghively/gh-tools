# Tdarr flow-plugin catalog — the full 85+ node reference

Indexed from `HaveAGitGat/Tdarr_Plugins/FlowPluginsTs/CommunityFlowPlugins/`
(frozen 2026-07-20). Every flow node Tdarr 2.x ships, organized by category.

The earlier `flows.md` covered the high-level system; this is the exhaustive
catalog of nodes you can use to build flows.

## Categories at a glance

| Category | Count | Purpose |
|---|---|---|
| `input` | 1 | Flow entry point |
| `basic` | 1 | Basic video/audio handling |
| `audio` | 4 | Audio filters + normalization |
| `video` | 8 | Video filters + health check |
| `file` | 26 | File property checks + file ops |
| `ffmpegCommand` | 17 | Build explicit ffmpeg commands |
| `handbrake` | 1 | HandBrake custom args |
| `classic` | 2 | Wrap 1.x plugins in flows |
| `automations` | 3 | System automation (sleep, NVENC detection) |
| `tools` | 22 | Variables, webhooks, notifications, routing, control flow |
| (deprecated) | varies | Old stuff, avoid |

**Total: ~85 nodes** — far more than the 1.x plugin catalog.

## `input/` — flow entry (1 node)

| Node | Purpose |
|---|---|
| `inputFile` | The mandatory entry point. Receives `args.inputFileObj` and `args.userVariables.*`. |

## `basic/` — basic media handling (1 node)

| Node | Purpose |
|---|---|
| `basicVideoOrAudio` | Routes the flow based on whether the file is video or audio. |

## `audio/` — audio filters + actions (4 nodes)

| Node | Purpose |
|---|---|
| `checkAudioCodec` | Filter by audio codec name(s). |
| `checkAudioBitrate` | Filter by audio bitrate range. |
| `checkChannelCount` | Filter by channel count (2/6/8). |
| `normalizeAudio` | Apply loudnorm audio normalization (EBU R128). |

## `video/` — video filters + analysis (8 nodes)

| Node | Purpose |
|---|---|
| `checkVideoCodec` | Filter by video codec. |
| `checkVideoResolution` | Filter by resolution class. |
| `checkVideoFramerate` | Filter by framerate. |
| `checkVideoBitrate` | Filter by video stream bitrate. |
| `checkOverallBitrate` | Filter by total file bitrate. |
| `check10Bit` | Detect 10-bit video (yes/no). |
| `checkHdr` | Detect HDR / Dolby Vision. |
| `runHealthCheck` | Run an inline health check as a flow step (the most powerful analysis node). |

## `file/` — file property checks + operations (26 nodes)

This is the biggest category — split into "checks" (filters) and "operations" (actions).

### File-property checks (analysis filters)

| Node | Purpose |
|---|---|
| `checkFileExists` | Verify a path exists. |
| `checkFileExtension` | Filter by extension. |
| `checkFileNameIncludes` | Filter by substring in filename. |
| `checkFileSize` | Filter by file size (bytes). |
| `checkFileMedium` | Detect video / audio / other. |
| `checkFileVariationExists` | Check if a variant/version exists (e.g. other resolutions). |
| `checkForHardlinks` | Detect hardlinks (storage management). |
| `checkFileChanged` | Detect modification since last flow run. |
| `checkStreamsCount` | Filter by total stream count. |
| `checkStreamProperty` | Generic stream-property filter (most flexible). |
| `compareFileSize` | Compare file size to a reference value. |
| `compareFileSizeRatio` | Compare size ratio (output/source). **Catch failed transcodes.** |
| `compareFileSizeRatioLive` | Same, live during transcode (bail out mid-stream). |
| `compareFileDurationRatio` | Compare duration ratio (output/source). **Catch A/V desync.** |
| `calculateFileHash` | Compute SHA/hash of file content (dedup, change-tracking). |

### File operations (writes — confirm-gate mentally)

| Node | Purpose |
|---|---|
| `setWorkingFile` | Define the working file (transcode target). |
| `copyToWorkDirectory` | Copy file to working dir. |
| `moveToOriginalDirectory` | Move file back to source location. |
| `moveToDirectory` | Move to specified directory. |
| `copyToDirectory` | Copy to specified directory. |
| `copyMoveFolderContent` | Folder-level bulk copy/move. |
| `replaceOriginalFile` | Replace source with working file (THE post-transcode step). |
| `renameFile` | Rename a file (e.g. codec-suffix). |
| `setFilePermissions` | chmod (Unraid/Linux perms). |
| `deleteFile` | Delete a file (irreversible). |
| `unpack` | Extract RAR/ZIP/etc (for downloaded multi-part archives). |

## `ffmpegCommand/` — explicit ffmpeg command builder (17 nodes)

These nodes chain together to build a single ffmpeg command. Order matters —
typically: `ffmpegCommandStart` → encoder selection → optional transforms →
`ffmpegCommandExecute`.

| Node | Purpose |
|---|---|
| `ffmpegCommandStart` | Begin the ffmpeg command chain (mandatory). |
| `ffmpegCommandSetContainer` | Set output container (mkv/mp4/...). |
| `ffmpegCommandSetVideoEncoder` | Pick video encoder (hevc_nvenc / libx265 / ...). |
| `ffmpegCommandSetVideoBitrate` | Set video bitrate. |
| `ffmpegCommandSetVdeoFramerate` | Set output framerate (resample). |
| `ffmpegCommandSetVdeoResolution` | Set output resolution (scale). |
| `ffmpegCommand10BitVideo` | Force 10-bit output. |
| `ffmpegCommandCropBlackBars` | Detect + crop letterbox bars. |
| `ffmpegCommandHdrToSdr` | Tone-map HDR → SDR (proper color conversion, not flag-strip). |
| `ffmpegCommandNormalizeAudio` | Audio loudnorm normalization. |
| `ffmpegCommandEnsureAudioStream` | Ensure at least one audio stream (silent fallback). |
| `ffmpegCommandRemoveSubtitles` | Strip all subtitles. |
| `ffmpegCommandRemoveDataStreams` | Strip data streams (cover art, etc.). |
| `ffmpegCommandRemoveStreamByProperty` | Generic stream removal by property. |
| `ffmpegCommandRorderStreams` | Reorder streams (video → audio → subs). |
| `ffmpegCommandCustomArguments` | Append arbitrary ffmpeg args. |
| `ffmpegCommandExecute` | Run the assembled command (mandatory final step). |

## `handbrake/` — HandBrake integration (1 node)

| Node | Purpose |
|---|---|
| `handbrakeCustomArguments` | Run HandBrake with custom args (alternative to ffmpeg for some workflows). |

## `classic/` — wrap 1.x plugins (2 nodes)

| Node | Purpose |
|---|---|
| `runClassicTranscodePlugin` | Run any classic 1.x transcode plugin as a flow step. |
| `runClassicFilterPlugin` | Run any classic 1.x filter plugin as a flow step. |

These are critical for backward compatibility — you can mix classic plugins
(`MC93_Migz1FFMPEG`, etc.) into a 2.x flow.

## `automations/` — system automation (3 nodes)

| Node | Purpose |
|---|---|
| `preventSleepWhileEncoding` | Keep the machine awake while transcodes run (prevent OS sleep / suspend). |
| `detectNonTdarrNvenc` | Detect NVENC processes from OTHER apps (avoid double-booking the GPU). |
| `runAutomation` | Generic automation runner. |

`detectNonTdarrNvenc` is gold for shared GPUs (gh-nvidia has ComfyUI +
Ollama + Tdarr all competing for the RTX 3060). It lets the flow check
"is something else using NVENC right now?" and wait or skip.

## `tools/` — the power-user category (22 nodes)

This is where the real flow capability lives. Includes variables, webhooks,
notification, control flow, file-system operations beyond the basic ones.

### Variables + arithmetic

| Node | Purpose |
|---|---|
| `setFlowVariable` | Set a flow variable (string/number/JSON). |
| `checkFlowVariable` | Branch on a flow variable value. |
| `arithmeticFlowVariable` | Math operations on variables. |

These enable loops, conditional logic, and accumulation across flow steps.

### Notification + integration

| Node | Purpose |
|---|---|
| `webRequest` | Call ANY HTTP endpoint (POST/GET/etc.). |
| `apprise` | Use [Apprise](https://github.com/caronc/apprise) — one URL supports 100+ notification services (Discord, Slack, Telegram, Pushbullet, ntfy, webhooks, email, SMS, etc.). |
| `notifyRadarrOrSonarr` | Notify *arr of a file change. |
| `applyRadarrOrSonarrNamingPolicy` | Rename file to *arr naming convention. |

### *arr / library integration

| Node | Purpose |
|---|---|
| `notifyRadarrOrSonarr` | Trigger *arr rescan. |
| `applyRadarrOrSonarrNamingPolicy` | Auto-rename per *arr standards. |
| `removeFromTdarr` | Remove file from Tdarr's DB (not from disk). |
| `requireReview` | Push file to staging queue for human review. |
| `processedAdd` / `processedCheck` | Track what's been processed in this flow (dedup). |

### Node + worker control

| Node | Purpose |
|---|---|
| `tagsWorkerType` | Route the flow to a node matching a tag (`mapped`, `unmapped`, custom). |
| `tagsRequeue` | Requeue the file to a different tagged node. |
| `pauseUnpauseAllNodes` | Pause or resume all nodes from within a flow. |
| `checkNodeHardwareEncoder` | Detect what hardware encoder the current node has. |
| `clearCache` | Clear the transcode cache mid-flow. |

### CLI + custom code

| Node | Purpose |
|---|---|
| `runCli` | Run ANY shell command on the node (e.g. ffprobe, MediaInfo, custom scripts). |
| `runMkvpropedit` | Use mkvpropedit for fast metadata edits (no re-encode). |
| `customFunction` | Run arbitrary JavaScript code in the flow (ultimate escape hatch). |

### Control flow

| Node | Purpose |
|---|---|
| `goToFlow` | Jump to a different point in the flow (loops, retries). |
| `waitTimeout` | Wait N seconds before continuing (polling, retries). |
| `comment` | Add a visible comment to the flow graph (documentation). |
| `failFlow` | Explicitly fail the flow (skip this file). |
| `onFlowError` | Define what happens on flow error (notify, log, etc.). |
| `resetFlowError` | Clear a previous error state. |

## Common flow patterns

### "Standard HEVC transcode + cleanup" (the typical starter)

```
inputFile
  → checkVideoCodec(invert: hevc, av1)    [skip already-HEVC/AV1]
  → ffmpegCommandStart
  → ffmpegCommandSetContainer(mkv)
  → ffmpegCommandSetVideoEncoder(hevc_nvenc)
  → ffmpegCommandCustomArguments(-preset p6 -tune hq -rc vbr -cq 21 -pix_fmt yuv420p10le)
  → ffmpegCommandExecute
  → compareFileSizeRatio(min:0.3, max:1.5)  [validate output]
  → replaceOriginalFile
  → webRequest(POST Emby /Library/Refresh)
```

### "Smart HDR preservation"

```
inputFile
  → checkHdr
  → if HDR:
      ffmpegCommandStart
      → ffmpegCommandSetVideoEncoder(hevc_nvenc)
      → ffmpegCommand10BitVideo
      → ffmpegCommandCustomArguments(-cq 18 -color_primaries bt2020 -color_trc smpte2084 -colorspace bt2020nc)
      → ffmpegCommandExecute
  → if SDR:
      ffmpegCommandStart
      → ffmpegCommandSetVideoEncoder(hevc_nvenc)
      → ffmpegCommandCustomArguments(-cq 21 -pix_fmt yuv420p10le)
      → ffmpegCommandExecute
  → replaceOriginalFile
```

### "Audio normalization with validation"

```
inputFile
  → checkAudioCodec(dts, truehd)
  → normalizeAudio
  → compareFileDurationRatio(min:0.99, max:1.01)  [verify no desync]
  → if fail: requireReview
  → else: replaceOriginalFile
```

### "Avoid GPU contention"

```
inputFile
  → detectNonTdarrNvenc
  → if NVENC busy:
      waitTimeout(60)
      → goToFlow(detectNonTdarrNvenc)  [loop]
  → else:
      [normal transcode flow]
```

### "Notify Discord on transcode"

```
inputFile
  → [transcode nodes]
  → onFlowError:
      apprise(discord://webhook_id/webhook_token, "Transcode failed: {{{args.inputFileObj._id}}}")
  → after success:
      apprise(discord://..., "Transcoded: {{{args.inputFileObj._id}}} (saved {{{args.flowVariables.sizeDiff}}} bytes)")
```

### "Mixed-node routing (mapped + unmapped)"

```
inputFile
  → tagsWorkerType(unmapped)
  → [transcode nodes on the powerful unmapped node]
  → tagsRequeue(mapped)  [route to mapped node for filesystem ops]
  → tagsWorkerType(mapped)
  → replaceOriginalFile  [now on a node that can write to the library]
```

## How to install flow plugins

Most flow plugins ship with Tdarr out of the box — they're built into the
server. Search for them via `tdarr_search_flow_plugins(string="normalizeAudio",
plugin_type="flow")` to confirm availability.

Some flow plugins are community-contributed and need installation via the
Flows tab → Flow+ → browse templates, OR via `tdarr_db(mode="insert",
collection="FlowsJSONDB", obj={...}, confirm=True)`.

## See also
- `flows.md` — high-level flows vs plugin stacks.
- `plugins.md` — classic 1.x plugin catalog.
- `media-analysis.md` — analysis-focused flow nodes in context.
- `audio-deep-dive.md` — audio-focused flow nodes in context.
