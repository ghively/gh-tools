# Emby customization cookbook (home screens, theming, intros, webhooks, audiobooks, organization)

The "make Emby yours" reference. Everything routes through existing tools;
writes preview-then-confirm as always.

## 1. Home screen customization — `emby_display_prefs`

Per-user, per-client. The 7 home rows are `homesection0`..`homesection6` in
CustomPrefs. Values:

| Value | Row |
|---|---|
| `smalllibrarytiles` | My Media (tiles) |
| `librarybuttons` | My Media (small buttons) |
| `resume` | Continue Watching |
| `resumeaudio` | Continue Listening |
| `nextup` | Next Up |
| `latestmedia` | Latest (per library) |
| `activerecordings` | Active Recordings |
| `none` | hide this slot |
| `""` | server default order |

Other high-value CustomPrefs: `accentColor` (theme accent), `enableLogoAsTitle`,
`skipForwardLength`/`skipBackLength` (ms), `stillwatchingms` ("are you still
watching" delay), `tvhome` (TV-optimized home). Example — kid-friendly minimal
home: `{"homesection0": "resume", "homesection1": "latestmedia",
"homesection2": "none", "homesection3": "none"}`.

## 2. Web UI theming & branding

Named store `branding` (`emby_get_config("branding")` /
`emby_set_config(patch, "branding")`):
- `LoginDisclaimer` — text on the login page.
- `CustomCss` — arbitrary CSS injected into the web UI (served anonymously at
  `/Branding/Css`). Theming examples: hide features
  (`.headerCastButton{display:none}`), dark accent overrides, custom fonts.
  Keep a copy of the CSS before replacing (round-trip rule applies).

## 3. Cinema intros (pre-roll trailers) — installed plugin

Store `cinemamode` (`emby_plugin_config("Cinema Intros")`):
`EnableIntrosForMovies`, `EnableIntrosForEpisodes`,
`EnableIntrosForWatchedContent`, trailer counts, and custom intro paths
(play your own bumper video before features). Per-user opt-out lives in user
Configuration (`EnableCinemaMode`).

## 4. Webhooks (event → Discord/Home Assistant/etc.) — installed plugin

Store `webhooks` (`emby_plugin_config("Webhooks")`): `{"Webhooks": [...],
"Events": [...]}`. Each webhook: url + event subscriptions (playback start/
stop, item added, user locked out...). Recipe: read store → append webhook
object → write back (confirm). Pair with `emby_activity` to verify firing.

## 5. Library types — the DEFINITIVE matrix (extracted from this server's own
## wizard code and each type live-verified by reversible create/delete)

| collection_type | Library | Notes |
|---|---|---|
| `movies` | Movies | |
| `tvshows` | TV shows | |
| `music` | Music | |
| `musicvideos` | Music videos | |
| `homevideos` | Home videos & photos | photos live here (no separate type) |
| `audiobooks` | Audiobooks | ✔ verified accepted on 4.7.14 |
| `books` | Books | ebooks AND comics — see below; ✔ verified |
| `games` | Games | string accepted ✔, but functional only with the GameBrowser plugin (the wizard itself says so) |
| `""` or `mixed` | Mixed content | multi-type; stored as null CollectionType (✔ verified) — the wizard sends null too |

Not library types on 4.7: **podcasts** (use the "Podcasts" plugin from the
catalog — it creates a channel), photos (part of homevideos), boxsets/
playlists (system-managed).

### Books & comics

- Create: `emby_library_manage("create", name="Books",
  collection_type="books", path="/mnt/Media/Books", confirm=true)`.
- Formats: epub, pdf, mobi/azw (ebooks); **cbz/cbr (comics/manga)** — the web
  client has a built-in reader for epub and cbz/cbr.
- Naming: one folder per book/series; comics as `Series Name/Series Name 001.cbz`
  (zero-padded issue numbers sort correctly). Emby reads embedded
  `ComicInfo.xml` from cbz archives when present.
- Metadata providers for books are thin — expect filename-based entries;
  curate with `emby_update_item` (item Type: "Book") and `emby_images`.

### Audiobooks

- Create with `collection_type="audiobooks"` (verified).
- Naming: one folder per book (`Author/Book Title/`), chapters as ordered
  files (`01 - Chapter.mp3`) or a single `.m4b` with chapters. Audio tags
  drive metadata (album = book, artist = author). Item Type: "AudioBook".
- Resume works like video; "Continue Listening" home row = `resumeaudio` (§1).
- Verify after scan: `emby_items(include_types="AudioBook", limit=10)`.

### Games (GameBrowser plugin — INSTALLED and live-verified 2026-07-15)

GameBrowser 3.2.9 is active on gh-media (id `4c2fda1c-fd5e-433a-ad2b-718e0b73e9a9`).
The reason game setups historically fail: **creating a games library is NOT
enough** — platforms must be configured in the PLUGIN config first.

Working setup flow (each step verified live; full details, extension table,
and metadata truth in **games-gamebrowser.md**):
1. Create the games library: `emby_library_manage("create", name="Games",
   collection_type="games", path=..., confirm=true)`. Content type MUST be
   games — mixed libraries never produce games.
2. Plugin config is a `GameSystems` array of `{"ConsoleType": "<platform>",
   "Path": "<DIRECT subfolder of the library path for that platform>"}` —
   `emby_plugin_config("GameBrowser", '{"GameSystems": [...]}', confirm=true)`.
   Folder NAMES are free-form (they become the display name) — it's the PATH
   + ConsoleType that must be right. Registering the library root itself does
   NOT work. NOTE: GameBrowser is the one plugin on this server that uses the
   LEGACY config route — emby_plugin_config resolves it automatically.
3. Verify registration: `emby_call("GET", "/GameBrowser/GamePlatforms")`
   echoes the configured systems. Then run a library scan.
4. Expect bare titles with no artwork — internet game metadata was REMOVED
   from the plugin in 2018 (TheGamesDb API died). Local images
   (`poster.jpg` / `<rom name>-poster.jpg`) work; see games-gamebrowser.md.

Valid `ConsoleType` values (all 48, extracted from the plugin's own config
page on this server — must match EXACTLY):
3DO, Amiga, Arcade, Atari 2600, Atari 5200, Atari 7800, Atari Jaguar,
Atari Jaguar CD, Atari XE, Colecovision, Commodore 64, Commodore Vic-20,
DOS, Intellivision, Xbox, Xbox 360, Xbox One, Neo Geo, Nintendo 64,
Nintendo 3DS, Nintendo DS, Game Boy, Game Boy Advance, Game Boy Color,
Gamecube, Nintendo (= NES), Nintendo Switch, Super Nintendo (= SNES),
Virtual Boy, Nintendo Wii, Nintendo Wii U, Sega 32X, Sega CD, Dreamcast,
Game Gear, Sega Genesis, Sega Master System, Sega Mega Drive, Sega Saturn,
Sony Playstation, PS2, PS3, PS4, PSP, TurboGrafx 16, TurboGrafx CD,
Windows, ZX Spectrum.

Maintenance status (checked 2026-07-15): GameBrowser lives in the official
MediaBrowser GitHub org — NOT archived, last push 2025-12, but commits are
sparse "compatibility update"s (~2/year). It is on LIFE SUPPORT: Emby keeps it
loading on current servers, no feature work. Catalog has 39 releases; 3.2.9
("Support more file extensions") requires Emby ≥ 4.6.0.50. Set expectations
accordingly: scanning/config verified working here; rich metadata is the weak
spot. Related: the **EmuMovies** catalog plugin provides game images (useful
because TheGamesDb metadata provider has API-availability problems). Game item
type for queries: `emby_items(include_types="Game")`; genres via `/GameGenres`.

### Mixed (multi-type) libraries

`collection_type="mixed"` (or "") — one library holding movies + TV + more.
Trade-offs: scanners must guess each folder's type, so metadata matching is
less reliable than dedicated libraries; per-type fetcher order is tunable via
LibraryOptions.TypeOptions. Prefer dedicated libraries unless the folder
structure is genuinely mixed.

### Library structure API gotcha (proven live)

DELETE/rename/path operations on `/Library/VirtualFolders` **500 (NRE) unless
the folder's `Guid` is passed as the `Id` query param** — Name alone is not
enough on 4.7.14. `emby_library_manage` handles this; remember it when using
`emby_call` directly.

## 6. Auto-organize (watch folder → renamed into library)

The official **Auto Organize** plugin (catalog name "Auto Organize") watches a
folder and moves/renames episodes & movies into your library structure.
Not currently installed on gh-media. Setup workflow:
1. `emby_install_plugin("Auto Organize", confirm=true)` → restart.
2. Configure via store `autoorganize` (`emby_plugin_config`): watch folder,
   target libraries, naming pattern, delete-empty-folders.
3. Its scan runs as a scheduled task; monitor results via
   `emby_call("GET", "/Library/FileOrganization", ...)` (endpoints register
   once the plugin is active — find them with emby_list_endpoints).

## 7. Task scheduling — `emby_task_triggers`

Maintenance windows: nightly scan at 03:00 =
`[{"Type": "DailyTrigger", "TimeOfDayTicks": 108000000000}]`
(1 h = 36,000,000,000 ticks). Weekly deep tasks (chapter images, DB optimize)
→ `WeeklyTrigger` + `DayOfWeek`. `[]` disables a task's automatic runs.

## 8. Config backup & restore (pure API — no plugin needed)

Snapshot everything writable to local JSON (the /emby-backup command runs
this):
1. `emby_get_config()` → server config.
2. Named stores: `encoding`, `livetv`, `notifications`, `subtitles`, `dlna`,
   `branding`, `devices`, plus plugin stores (from
   `emby_plugin_config()` page list).
3. Per-user: `emby_user(u)` (Policy + Configuration) for each user;
   `emby_display_prefs(u)`.
4. Per-library: `emby_library_manage("get_options", name)` + paths.
5. Live TV: tuners + guide providers (`emby_livetv_status`).
Restore = round-trip writes of the saved objects (confirm each domain).
The official **Backup** plugin ("Server Configuration Backup") additionally
covers watch history/DB — recommend installing it for full disaster recovery.

## 9. Notification toggles (which events notify admins)

Store `notifications`: per-event `Options` array (Type, Enabled, SendToUsers,
DisabledMonitorUsers). Event types from `emby_call("GET",
"/Notifications/Types")`. Post a manual admin notification:
`emby_call("POST", "/Notifications/Admin", body='{"Name": "...",
"Description": "..."}')`.

## 10. Per-user playback defaults

User Configuration (round-trip `emby_call("POST", "/Users/{id}/Configuration",
body=<full merged object>)`): `AudioLanguagePreference`,
`SubtitleLanguagePreference`, `SubtitleMode` (Default/Always/OnlyForced/None/
Smart), `EnableNextEpisodeAutoPlay`, `RememberAudioSelections`,
`HidePlayedInLatest`, `EnableCinemaMode`.
