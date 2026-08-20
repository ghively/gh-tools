# Emby API map — all service domains, audited live (4.7.x, media-host, 2026-07)

484 operations across 392 paths, discovered from the server's own `/openapi.json`
(search it live with `emby_list_endpoints`). Every domain below was probed with real
calls. Verdicts: **works** (verified live), **dep-gated** (API fine, a dependency
isn't set up on this server), **hard-limit** (broken/absent in this build).

| Domain (tag) | Ops | Verdict | Notes / go-to endpoints |
|---|---|---|---|
| SystemService | 13 | works | Info, Configuration, Logs (`/System/Logs/Log?Name=`), Restart, Shutdown. `/System/Logs/{Name}` + `/Lines` 500 on 4.7 — use `?Name=` form |
| ConfigurationService | 4 | works | Full + named stores (`encoding`, `livetv`, `notifications`, `subtitles`, `dlna`, plugin stores). Round-trip writes! |
| UserService | 18 | works | CRUD, Policy, Password, Configuration. `/Users` and `/Users/{id}` verified |
| UserViewsService | 1 | works | `/Users/{id}/Views` (home-screen libraries) |
| UserLibraryService | 15 | works | Per-user item detail, latest, resume, played/favorite writes |
| LibraryService | 31 | works | VirtualFolders, Refresh, counts, DeleteInfo is the ONE broken op (500 NRE on this build; DELETE /Items/{id} itself routes fine) |
| LibraryStructureService | 10 | works | Curated: `emby_library_manage`. All 9 library types live-verified (movies/tvshows/music/musicvideos/homevideos/audiobooks/books/games/mixed→null). GOTCHA: delete/rename/paths 500 unless the folder Guid is passed as `Id` |
| ItemsService | 3 | works | `/Items` — the universal query engine (filters, sorts, paging) |
| ItemUpdateService | 2 | works | `emby_update_item` + `emby_bulk_update` (query-wide patch with LockedFields auto-lock) |
| VideosService (mgmt) | 3 | works | `emby_versions`: MergeVersions/AlternateSources — 5 real duplicate groups found on server |
| ItemRefreshService | 1 | works | `POST /Items/{id}/Refresh` (modes + Replace flags) |
| ItemLookupService | 13 | works | Curated: `emby_identify` (providers/search/apply — verified against TheMovieDb live) |
| TvShowsService | 4 | works | NextUp, Seasons, Episodes, Upcoming (need `UserId` + series id) |
| MoviesService | 1 | works | `/Movies/Recommendations?UserId=` |
| SuggestionsService | 1 | works | `/Users/{id}/Suggestions` |
| CollectionService | 4 | works | Curated deep: `emby_collection` — query-create, smart sync, reverse lookup (ListItemIds), franchise finder (61 collections on server). TmdbCollectionName field is 4.8+ (absent here) |
| PlaylistService | 6 | works | Create, items, add/remove (0 playlists currently on server) |
| PlaystateService | 12 | works | Played/unplayed, playback progress reporting |
| SessionsService | 20 | works | Sessions list, Playing/{Command}, Command, Message, Play. 7 live sessions observed |
| MediaInfoService | 6 | works | `/Items/{id}/PlaybackInfo`, BitrateTest (needs `Size` param) |
| EncodingInfoService | 3 | works | Codec/encoder inventory |
| FfmpegOptionsService / ToneMapOptionsService / SubtitleOptionsService | 7 | works | Encoding-related option objects |
| PluginService | 6 | works* | List/uninstall fine. `/Plugins/{id}/Configuration` + `/Thumb` **500 for all 18 modern plugins** → use named stores (see plugin-management.md). SecurityInfo: Premiere ACTIVE |
| PackageService | 6 | works | 133-package catalog, install/cancel. `/Packages/{Name}` wants `AssemblyGuid` |
| ScheduledTaskService | 6 | works | 20 tasks; run/stop; curated trigger editing: `emby_task_triggers` |
| ActivityLogService | 1 | works | 1142 entries at audit time |
| DeviceService | 8 | works | 17 devices; options, camera-upload endpoints |
| NotificationsService / NotificationsApi | 8 | works* | Types/categories/user notifications fine. `/Notifications/Services` is EMPTY — no delivery plugins installed (Webhooks plugin covers outbound events instead) |
| EnvironmentService | 7 | works | DirectoryContents, Drives, DefaultDirectoryBrowser verified (server-side FS browse). NetworkShares needs a reachable SMB host |
| GenresService / MusicGenresService / GameGenresService / StudiosService / PersonsService / ArtistsService / TagService / OfficialRatingService / TrailersService | ~25 | works | By-name detail needs the EXACT entity name (else 500 NRE) |
| InstantMixService | 8 | works | Verified with real artist/genre ids |
| ImageService | 49 | works | Curated: `emby_images` (list/search/download/delete; providers TheMovieDb/TheTVDB/FanArt verified). Delivery verified via Range (206) |
| ImageByNameService | 6 | works* | Endpoints fine; General/Ratings/MediaInfo image packs simply not installed → 404 empty |
| RemoteImageService | 4 | works | `/Items/{id}/RemoteImages` verified; Download route present |
| DisplayPreferencesService | 2 | works | Curated: `emby_display_prefs` — home screen rows (homesection0-6), accent color, per user/client |
| LocalizationService | 4 | works | Cultures, countries, parental ratings, localization options |
| BrandingService | 3 | works | CSS/config (empty on this server) |
| DashboardService | 3 | hard-limit | Legacy web-UI internals (`/web/strings` etc.) — irrelevant to control |
| OpenApiService | 4 | works | The self-describing spec |
| DlnaService / DlnaServerService | 16 | works | 20 profiles listed; server itself disabled in `dlna` store (`EnableServer: false`, PlayTo on) |
| LiveTvService | 66 | **works** (unconfigured) | Largest domain; 6 curated tools (`emby_livetv_*`). Setup write path PROVEN live+reversibly (tuner add → IsEnabled true → delete → restored). No tuner/guide configured yet; m3u + hdhomerun tuner types, xmltv + embygn guide types available. Emby VALIDATES the M3U URL at add time (unreachable → 500, nothing created); channels import async via "Refresh Guide" task. See livetv.md |
| SyncService | 24 | works | Curated: `emby_sync_jobs` (targets/jobs/create/cancel — incl. media CONVERSION targets). Premiere active; 5 targets, 1 live job. `/Sync/Options` needs `UserId`+`ItemIds`+`TargetId` or it 500s |
| ConnectService | 5 | dep-gated | Emby Connect not linked on this server (404s). Link via dashboard with an emby.media account |
| GamesService | 1 | works* | Empty (no game libraries) |
| ChannelService | 1 | works | Media channels query |
| SubtitleService | 11 | works | Curated: `emby_subtitles` (list/search/download/delete — Open Subtitles verified live, 15 results for test movie) |
| AudioService / VideoService / VideoHlsService / DynamicHlsService / UniversalAudioService / HlsSegmentService / BifService | ~30 | works (delivery) | Player-facing media/stream delivery; BIF/images verified via Range requests. Not for model consumption — hand URLs to players |

## Practical substitution notes (learned during audit)

- 500 "Object reference not set" = wrong/nonexistent entity id or name, or missing
  dependency — NOT a server crash. Verify the id first (`emby_search`).
- By-name endpoints (`/Artists/{Name}`, `/Persons/{Name}`...) want exact names —
  get them from the corresponding list endpoint first.
- `/Shows/{Id}/Seasons|Episodes` need a SERIES id (movie ids 404) + `UserId`.
- Query params are PascalCase (`IncludeItemTypes`, `SortBy`, `Recursive`).
- Media/image delivery endpoints support `Range` headers (206).
