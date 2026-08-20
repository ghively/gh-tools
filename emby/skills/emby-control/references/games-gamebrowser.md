# GameBrowser — definitive setup & troubleshooting (Emby 4.7.14, plugin 3.2.9)

> **Live status on media-host (2026-07-15):** GameBrowser 3.2.9 INSTALLED and
> active (GUID `4c2fda1c-fd5e-433a-ad2b-718e0b73e9a9`). Config write +
> `/GameBrowser/GamePlatforms` registration proven reversibly via
> `emby_plugin_config` (legacy config route — the only plugin here using it).
> Everything below is sourced from the plugin's actual source at the v3.2.9
> commit (`50a555ebabeb`), the Emby catalog feed, and Emby-staff forum posts.

**Repo:** github.com/MediaBrowser/GameBrowser — public, not archived, but
LIFE SUPPORT: since 2022 only SDK "compatibility update" commits (~2/yr).
**Version a 4.7 server gets:** 3.2.9 (2022-02-10, requires ≥ 4.6.0.50).
3.3.0–3.3.3 need Emby 4.8; 3.3.4+ need the 4.9 beta.

## The #1 myth (why old guides fail)

`GameSystemDefinitions.cs` / "exact platform folder names" is a pre-2016
Media Browser 3 relic — it does not exist in any 3.x version. **Platform
identity comes ONLY from the plugin config**: `GameSystems` array of
`{"Path": <folder>, "ConsoleType": <dropdown value>}`. Folder NAMES are
free-form (they become the Game System's display name). What must match
exactly:
1. The configured **Path** vs the on-disk path Emby scans (case-insensitive
   verbatim compare — mapped-drive vs UNC mismatches break it).
2. The **ConsoleType** string (48 valid values — see customization.md §Games).

## Hard structural rules (from resolver source)

- Library content type must be exactly **Games** (`collection_type="games"`).
  A Mixed library NEVER produces games.
- Each platform folder must be a **direct subfolder of the library path** and
  registered in the plugin config. Registering the library root as the
  platform does NOT work (Emby never resolves the root, and 3.2.9's
  GameResolver requires a GameSystem parent).
- Every file with a matching extension anywhere under a registered platform
  folder becomes a Game (per-game subfolders are fine). The game's Album =
  the platform folder's name.
- After ANY GameSystems change: run a library scan.

```
/mnt/Media/Games            ← games library path
├── N64/                    ← registered: ConsoleType "Nintendo 64"
│   ├── Super Mario 64.z64
│   └── GoldenEye 007/GoldenEye 007.n64
├── Playstation/            ← registered: "Sony Playstation"
│   └── Final Fantasy VII.pbp
└── Arcade/                 ← registered: "Arcade"
    └── xmcota.zip          ← MAME short-name → "X-Men: Children of the Atom"
```

## Extensions accepted per ConsoleType (v3.2.9 — the 4.7 build)

| ConsoleType | Extensions |
|---|---|
| 3DO | .iso .cue |
| Amiga | .iso .adf |
| Arcade | .zip .7z (MAME short-name lookup via embedded list; BIOS zips NOT filtered — keep them out) |
| Atari 2600 | .bin .a26 |
| Atari 5200 | .bin .a52 |
| Atari 7800 | .a78 |
| Atari XE | .rom |
| Atari Jaguar | .j64 .zip |
| Atari Jaguar CD | .iso |
| Colecovision | .col .rom |
| Commodore 64 | .d64 .g64 .prg .tap .t64 |
| Commodore Vic-20 | .prg |
| DOS | .gbdos .disc (placeholder files) |
| Intellivision | .int .rom |
| Xbox | .disc .iso |
| Xbox 360 | .disc .iso |
| Xbox One | .disc (placeholder) |
| Neo Geo | .zip .iso |
| Nintendo 64 | .z64 .v64 .usa .jap .pal .rom .n64 .zip |
| Nintendo 3DS | .3ds .cia |
| Nintendo DS | .nds .zip |
| Game Boy | .gb .zip |
| Game Boy Advance | .gba .zip |
| Game Boy Color | .gbc .zip |
| Gamecube | .iso .bin .img .gcm .gcz .rvz |
| Nintendo (NES) | .nes .zip |
| Nintendo Switch | .xci .nsp |
| Super Nintendo | .smc .zip .fam .rom .sfc .fig |
| Virtual Boy | .vb |
| Nintendo Wii | .iso .dol .ciso .wbfs .wad .gcz .rvz |
| Nintendo Wii U | .disc .wud .wux |
| Sega 32X | .iso .bin .img .zip .32x |
| Sega CD | .iso .bin .img .chd |
| Dreamcast | .chd .gdi .cdi .bin .cue |
| Game Gear | .gg .zip |
| Sega Genesis | .smd .bin .gen .zip .md |
| Sega Master System | .sms .sg .sc .zip |
| Sega Mega Drive | .smd .zip .md |
| Sega Saturn | .iso .bin .img .chd |
| Sony Playstation | .iso .cue .img .ps1 .pbp .chd |
| PS2 | .iso .bin .chd |
| PS3 / PS4 | .disc (placeholder) |
| PSP | .iso .cso (.chd only on 4.9-era builds) |
| TurboGrafx 16 | .pce .zip |
| TurboGrafx CD | .bin .iso |
| Windows | .gbwin .disc (placeholder) |
| ZX Spectrum | .z80 .tap .tzx |

PSVita: not selectable on 4.7/4.8 (dropdown option is 3.3.5+/Emby 4.9 only).
`.disc`/`.gbdos`/`.gbwin` = empty placeholder text file named after the game.
Multi-disc: NO m3u support in any release — every disc/track lists separately;
use single-file formats (.chd/.pbp/single .iso). For Sega CD/Saturn/PS2/
Genesis/32X/TurboGrafx-CD, bin/cue rips duplicate per .bin track (its .bin is
a listed extension) — prefer .chd.

## Metadata: there is NONE (by design, since 2018)

TheGamesDb providers were deleted from the plugin in Sept 2018 when TGDB's
legacy API died; the plugin was never ported to the new keyed API. Emby staff
(Luke): "There is no internet metadata anymore…", "Games are currently XML
only" (no NFO for games on 4.7/4.8). So: bare filenames + no art after scan =
EXPECTED, not broken. Working metadata paths:
- **Local images** (confirmed working): per-game folder → `folder.jpg`/
  `poster.jpg` (+ `fanart.jpg`); loose ROMs → `<exact rom filename>-poster.jpg`
  next to the file.
- **Emby XML** via "Save metadata into media folders" + web-UI edits (or
  generate images/XML externally with Skyscraper/Skraper/LaunchBox exports).
- **`emby_images(item, "download", url=...)`** accepts any image URL — bulk
  art attachment can be scripted through the MCP tools.
- **EmuMovies plugin** (split out of GameBrowser in 2022; in the catalog) —
  fan-art image provider; requires an EmuMovies account. Untested here.

## Launching games

Not a server feature: the web app has never supported launching; the new
Windows app still lacked external players as of mid-2025. Legacy Emby Theater
for Windows can launch via per-system external players. Treat Emby as the
shelf, an emulator frontend as the player.

## Troubleshooting quick list

| Symptom | Fix |
|---|---|
| No games at all | Library type not Games; platform folder not registered; registered the library ROOT instead of a subfolder; forgot to rescan |
| One platform missing | Configured Path ≠ scanned path (UNC vs mount); or extension not accepted for that ConsoleType (table above) |
| Filenames, no art | Expected — see Metadata section |
| Discs duplicated | Convert to .chd/.pbp; no m3u support |
| Cryptic MAME names | Short name missing from embedded list — rename or edit metadata |
| BIOS zips listed as games | Move them out of the arcade folder |

Full source citations: v3.2.9 resolver/config at commit 50a555ebabeb;
catalog feed mb3admin.com EmbyPackages.json; provider deletion between trees
8c2aac6c → ee795240; emby.media forum threads 66006, 99068, 54915, 140192.
