# Tdarr community plugin catalog

Indexed from `HaveAGitGat/Tdarr_Plugins/Community/` (frozen 2026-07-19, 107
plugins). Use this to pick plugins for your workflow stacks.

Plugin IDs follow the pattern `Tdarr_Plugin_<id>_<Author>_<Description>`. Use
`tdarr_search_plugins(string="...")` to find them on your running Tdarr; use
`tdarr_install_plugin(plugin_id="...")` to install.

## By purpose

### HEVC transcoders (the core of "Standardize-on-HEVC")

| Plugin | Author | Engine | Notes |
|---|---|---|---|
| `MC93_Migz1FFMPEG` | Migz | **NVENC** (hevc_nvenc) | The benchmark. NVENC HEVC, configurable CQ, video+audio copy. Best for RTX 3060. |
| `MC93_Migz1FFMPEG_CPU` | Migz | CPU (libx265) | libx265 software fallback when no GPU. |
| `MC93_Migz1Remux` | Migz | remux only | Lossless container/stream cleanup. |
| `s7x9_winsome_h265_nvenc` | winsome | NVENC | Alternative HEVC NVENC. |
| `s7x9_winsome_h265` | winsome | CPU | libx265 8-bit. |
| `s7x9_winsome_h265_10bit` | winsome | CPU | libx265 10-bit (better banding). |
| `s7x8_winsome_h265` | winsome | CPU | Older winsome HEVC variant. |
| `A47j_FFMPEG_NVENC_HEVC_Video_Only` | A47j | NVENC | HEVC NVENC video-only (drops audio re-encode). |
| `075a_FFMPEG_HEVC_Generic` | (075a) | CPU | Generic HEVC. |
| `075b_FFMPEG_HEVC_Generic_Video_Audio_Only` | (075b) | CPU | HEVC, audio only (drop subs). |
| `075c_FFMPEG_HEVC_Generic_Video_Audio_Only_CRF20` | (075c) | CPU | HEVC at CRF 20. |
| `075d_FFMPEG_HEVC_GPU_Generic_Video_Audio_Only_CRF20` | (075d) | NVENC | GPU HEVC at CRF 20. |
| `b38x_Nosirus_h265_aac_no_meta` | Nosirus | CPU | HEVC + AAC + strip metadata. |
| `r002_rootuser_FFMPEG_HQ_HEVC_MKV_Animation` | rootuser | CPU | HEVC tuned for animation (flat colors). |
| `raf4_Floorpie_FFmpeg_Tiered_HEVC_MKV` | Floorpie | CPU | Tiered CRF by resolution. |
| `bsh1_Boosh_FFMPEG_QSV_HEVC` | Boosh | QSV | Intel QuickSync HEVC. |
| `Mthr_VaapiHEVCTranscode` | Mthr | VAAPI | Linux AMD/Intel VAAPI HEVC. |
| `JB69_JBHEVCQSV_MinimalFile` | JB69 | QSV | QuickSync HEVC minimal-output. |

### 4K / HDR specialists

| Plugin | Notes |
|---|---|
| `s710_nick_h265_nvenc_4K` | NVENC HEVC tuned for 4K with HDR preservation. |
| `fd5T_Sparticus_4K_AC3_No_Subs` | 4K → AC3 audio, strip subs. |

### H.264 transcoders

| Plugin | Notes |
|---|---|
| `a8hc_HaveAGitGat_HandBrake_H264_VeryFast1080p30_Y420` | HandBrake H.264 veryfast. |
| `a9hc_HaveAGitGat_HandBrake_H264_Fast1080p30` | HandBrake H.264 fast. |
| `SV6x_Smoove1FFMPEG_NVENC_H264` | NVENC H.264. |
| `077b_HandBrake_NVENC_264_Configurable` | HandBrake with NVENC H.264. |
| `da11_Dallas_FFmpeg_Presets_H264_MP4` | FFmpeg H.264 to MP4. |
| `e3jc_Tharic_H.264_MKV_480p30_No_Subs_No_Title_Meta` | H.264 480p cap. |
| `e3jd_Tharic_H.264_MKV_720p30_No_Subs_No_Title_Meta` | H.264 720p cap. |
| `e3je_Tharic_H.264_MKV_1080p30_No_Subs_No_Title_Meta` | H.264 1080p cap. |

### Tiered / configurable transcoders (recommended for mixed libraries)

| Plugin | Notes |
|---|---|
| `vdka_Tiered_CPU_CRF_Based_Configurable` | CPU, tiered CRF per resolution, fully configurable. **Best for CPU-only nodes.** |
| `vdka_Tiered_NVENC_CQV_BASED_CONFIGURABLE` | NVENC, tiered CQ per resolution, fully configurable. **Best for mixed-resolution libraries on GPU nodes.** |
| `d5d3_iiDrakeii_FFMPEG_NVENC_Tiered_MKV` | NVENC tiered. |
| `DOOM_NVENC_Tiered_MKV_CleanAll` | NVENC tiered + clean streams. |
| `drdd_standardise_all_in_one` | All-in-one standardize. |
| `075a_Transcode_Customisable` | Generic configurable. |

### AV1 / VP9

| Plugin | Notes |
|---|---|
| `VP92_VP9_Match_Bitrate_One_Pass` | VP9 with matched bitrate (1-pass). |

(No AV1 plugins in the community catalog as of 2026-07. Use custom plugin +
`libsvtav1` if you want AV1.)

### Audio transcoders / cleaners

| Plugin | Purpose |
|---|---|
| `MC93_Migz3CleanAudio` | Remove unwanted audio tracks (keep-list configurable). |
| `MC93_Migz5ConvertAudio` | Convert specific audio codecs (e.g. DTS → EAC3). |
| `00td_action_add_audio_stream_codec` | Add an audio stream of a specific codec. |
| `00td_action_keep_one_audio_stream` | Keep only one audio track. |
| `00td_action_remove_audio_by_channel_count` | Remove by channel count (e.g. drop 7.1). |
| `00td_action_standardise_audio_stream_codecs` | Standardize audio codecs. |
| `a9hd_FFMPEG_Transcode_Specific_Audio_Stream_Codecs` | Transcode specific audio codecs. |
| `a9he_New_file_size_check` | Filter by resulting file size. |
| `b39x_the1poet_surround_sound_to_ac3` | Convert surround → AC3. |
| `f4k1_aune_audio_to_flac` | Convert audio to FLAC. |
| `c0r1_SetDefaultAudioStream` | Set the default audio track. |
| `henk_Add_Specific_Audio_Codec` | Add an audio codec if missing. |
| `henk_Keep_Native_Lang_Plus_Eng` | Keep native language + English audio. |
| `jeons001_Downmix_to_stereo_and_apply_DRC` | Downmix to stereo with dynamic range compression. |
| `jordy_filter_by_audio_codec_and_channels` | Filter by audio codec + channel count. |
| `jordy_Remove_Audio_By_Codec_Channels` | Remove audio by codec/channel count. |
| `NIfPZuCLU_2_Pass_Loudnorm_Audio_Normalisation` | 2-pass loudness normalization (EBU R128). |
| `MP01_MichPasCleanSubsAndAudioCodecs` | Clean subs + audio codecs. |

### Subtitle transcoders / cleaners

| Plugin | Purpose |
|---|---|
| `MC93_Migz4CleanSubs` | Remove unwanted subtitle tracks. |
| `00td_action_remux_container` | Remux (preserves subs). |
| `078d_Output_embedded_subs_to_SRT_and_remove` | Extract embedded subs to SRT, remove originals. |
| `rr01_drpeppershaker_extract_subs_to_SRT` | Extract subs to SRT (alternative). |
| `e5c3_CnT_Add_Subtitles` | Add subtitles from external files. |
| `x7ab_Remove_Subs` | Strip all subtitles. |
| `x7ac_Remove_Closed_Captions` | Strip CEA-608/708 closed captions. |
| `sdd3_Remove_Commentary_Tracks` | Remove commentary audio. |
| `sdf5_Thierrrrry_Remove_Non_English_Audio` | Remove non-English audio. |

### Stream order / metadata / container

| Plugin | Purpose |
|---|---|
| `MC93_Migz6OrderStreams` | Order streams: video → audio → subtitles. |
| `00td_action_re_order_all_streams_v2` | Generic stream reorder. |
| `076a_re_order_audio_streams` | Reorder audio streams. |
| `076b_re_order_subtitle_streams` | Reorder subtitle streams. |
| `lmg1_Reorder_Streams` | Another reorder variant. |
| `MC93_Migz2CleanTitle` | Strip metadata title fields. |
| `MC93_MigzImageRemoval` | Remove embedded cover-art images. |
| `nc7x_Drawmonster_No_Title_Meta` / `hk75_Drawmonster_MP4_AAC_No_Subs_No_metaTitle` / `hk76_GilbN_MP4_AAC_No_metaTitle` / `a37x_Drawmonster_MP4_No_Title_Meta` | Various MP4 normalization variants. |
| `00td_action_remux_container` | Remux container (MKV/MP4). |
| `vdka_Remove_DataStreams` | Strip data streams. |

### Filter library (Tdarr 2.x flow nodes too)

These are the building blocks of Tdarr 2.x flows but also usable as 1.x
"filter" plugins. Use them to gate transcodes.

| Plugin | Filters by |
|---|---|
| `00td_filter_by_codec` | Video / audio codec. |
| `00td_filter_by_resolution` | Resolution (e.g. only 1080p). |
| `00td_filter_by_size` | File size. |
| `00td_filter_by_bitrate` | Bitrate. |
| `00td_filter_bit_depth` | Bit depth (8 vs 10). |
| `00td_filter_by_codec_tag_string` | Codec tag string. |
| `00td_filter_by_file_property` | Generic file property. |
| `00td_filter_by_stream_tag` | Stream tag. |
| `00td_filter_break_stack_if_processed` | Control-flow: stop stack if file was processed. |
| `tsld_filter_modified_date` | Filter by file modified date. |
| `d5d4_iiDrakeii_Not_A_Video_Mjpeg_Fix` | Detect Mjpeg mislabeled as video. |

### File / library management

| Plugin | Purpose |
|---|---|
| `z18s_rename_files_based_on_codec` | Rename by codec. |
| `z18t_rename_files_based_on_codec_and_resolution` | Rename by codec + resolution. |
| `scha_rename_based_on_codec_schadi` | Rename by codec (variant). |
| `z80t_keep_original_date` | Preserve original mtime. |
| `O8O0dCTlb_Set_File_Permissions_For_UnRaid` | Set file permissions (Unraid-specific). |
| `43az_add_to_radarr` | Add file to Radarr. |
| `MC93_MigzPlex_Autoscan` / `TD01_TOAD_Autoscan` / `goof1_URL_Plex_Refresh` | Trigger media-server library scan after transcode. |

### Validation / health checks

| Plugin | Purpose |
|---|---|
| `a9hf_New_file_duration_check` | Filter files by duration. |
| `a9he_New_file_size_check` | Filter files by size. |

### Misc / niche

| Plugin | Purpose |
|---|---|
| `e5c3_CnT_Remove_Letterbox` | Detect + crop letterbox bars. |
| `e5c3_CnT_Keep_Preferred_Audio` | Keep preferred audio language. |
| `00td_action_transcode` | Generic transcode action. |
| `00td_action_remove_stream_by_specified_property` | Remove streams by property. |
| `00td_action_handbrake_basic_options` / `00td_action_handbrake_ffmpeg_custom` | HandBrake basic / custom. |
| `ER01_Transcode audio and video with HW (PC and Mac)` | Cross-platform HW transcode. |
| `Greg_MP3_FFMPEG_CPU` | MP3 audio transcode. |
| `JB69_JBHEVCQSZ_PostFix` | HEVC QSV post-fix. |
| `z1ab_TheRealShadoh_FFmpeg_Subs_H264_Fast/Slow/VeryFast/Medium` | H.264 + subs transcodes at various presets. |

## Recommended starter stacks

For a homelab with NVIDIA GPU (unraid-host) targeting library-size reduction:

**Stack 1: Aggressive HEVC (max savings)**
1. `MC93_Migz1FFMPEG` (NVENC HEVC, CQ 21, 10-bit)
2. `MC93_Migz3CleanAudio` (keep English + commentary)
3. `MC93_Migz4CleanSubs` (keep English)
4. `MC93_Migz2CleanTitle` (strip title metadata)
5. `MC93_MigzImageRemoval` (drop cover-art spam)
6. `MC93_Migz6OrderStreams`

**Stack 2: Conservative remux (no quality loss)**
1. `MC93_Migz1Remux`
2. `MC93_Migz3CleanAudio`
3. `MC93_Migz4CleanSubs`
4. `MC93_Migz6OrderStreams`

**Stack 3: Compatibility (for Apple/web-facing share)**
1. `SV6x_Smoove1FFMPEG_NVENC_H264` (NVENC H.264 8-bit)
2. `MC93_Migz5ConvertAudio` (DTS/TrueHD → EAC3)
3. `00td_action_remux_container` (MP4 output)
4. `MC93_Migz6OrderStreams`

Install each via `tdarr_install_plugin(plugin_id="Tdarr_Plugin_MC93_Migz1FFMPEG",
confirm=True)` and arrange in a library's plugin stack via the UI.

## How to find new plugins

```python
# Search by author
tdarr_search_plugins(string="Migz", plugin_type="standard")
# Search by purpose
tdarr_search_plugins(string="HEVC", plugin_type="standard")
tdarr_search_plugins(string="NVENC", plugin_type="standard")
# List flow plugins
tdarr_search_flow_plugins(string="", plugin_type="flow")
```

To browse the upstream catalog directly:
<https://github.com/HaveAGitGat/Tdarr_Plugins/tree/master/Community>

## See also
- `flows.md` — Tdarr 2.x flow system (the visual node-graph successor to plugin stacks).
- `workflows.md` — how the plugins above combine into end-to-end transcode pipelines.
