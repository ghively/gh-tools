# CONFIGURATION.md — Emby Server Configuration via REST API (Emby 4.7.x, Linux)

> **Live-verified deltas for media-host (4.7.x):** `GET /Users` works (as does
> `/Users/Query`). `POST /System/Configuration/Partial` is a newer-server route —
> do not assume it on 4.7.14; the round-trip pattern below always works and is
> what the `emby_set_config` tool implements. Named stores verified live here:
> `encoding`, `livetv`, `notifications`, `subtitles`, `dlna`, plus plugin stores
> `opensubtitles`, `webhooks`, `cinemamode`, `fanart`, `musicbrainz`.

Reference for controlling Emby Server configuration through its REST API. Accurate to Emby
(NOT Jellyfin — the projects diverged in 2018 and their config models are different).
Written against Emby Server 4.7.x on Linux; version-specific caveats are flagged.

## 1. API fundamentals

- Base URL pattern: `http[s]://host:8096/emby/{apipath}` (the `/emby/` prefix is optional but
  canonical). HTTPS default port is 8920.
- Formats: JSON or XML, controlled by `Content-Type: application/json` / `application/xml`.
- **API key auth** (right choice for automation): create a key in Dashboard → Advanced →
  Security ("Api Keys"). Pass it either as query parameter `?api_key=KEY` or as HTTP header
  `X-Emby-Token: KEY`. Admin-level endpoints (everything in this document) require an admin key.
- **User auth** (interactive clients): `POST /Users/AuthenticateByName` with an
  `Authorization: Emby UserId="", Client="...", Device="...", DeviceId="...", Version="..."`
  header and the credentials in the body; the response's `AccessToken` is then sent as
  `X-Emby-Token`. `POST /Sessions/Logout` revokes it; a 401 means the token was revoked.
- Interactive API browser: Dashboard → Advanced → API (or `http://host:8096/emby/swagger`);
  static browser at `http://swagger.emby.media/?staticview=true`.

Example:

```
curl -H "X-Emby-Token: $KEY" http://server:8096/emby/System/Configuration
```

Sources:
- https://dev.emby.media/doc/restapi/index.html
- https://dev.emby.media/doc/restapi/API-Key-Authentication.html
- https://dev.emby.media/doc/restapi/User-Authentication.html

## 2. How Emby stores configuration

All configuration is XML files under the server data folder — on Linux: **`/var/lib/emby`**
(Synology DSM 7: `/volume1/@appdata/EmbyServer`; Windows: `%AppData%\Emby-Server\programdata`).

- `config/system.xml` — the main `ServerConfiguration` object.
- `config/encoding.xml` — transcoding options (`encoding` named configuration).
- `config/dlna.xml`, `config/livetv.xml`, `config/notifications.xml`, `config/devices.xml`,
  `config/branding.xml`, plus one file per plugin-registered named configuration
  (e.g. `autoorganize.xml`, `xbmcmetadata.xml`).
- `users/` + `users.db` — user records; policy/configuration are edited via API, not files.
- Library settings live per-library (`LibraryOptions`), edited via the VirtualFolders API.

Never hand-edit these files while the server is running; the server rewrites them and your
edits will be lost. Use the API (server applies changes live and persists them itself).

Sources:
- https://emby.media/support/articles/Server-Data-Folder.html
- ConfigurationStore registrations in the open-source lineage, e.g.
  https://github.com/MediaBrowser/Emby/blob/master/Emby.Dlna/ConfigurationExtension.cs

## 3. The configuration endpoints (ConfigurationService)

| Method | Path | Purpose |
|---|---|---|
| GET  | `/System/Configuration` | Get the full `ServerConfiguration` |
| POST | `/System/Configuration` | Replace the full `ServerConfiguration` |
| GET  | `/System/Configuration/{Key}` | Get a *named* configuration (e.g. `encoding`) |
| POST | `/System/Configuration/{Key}` | Replace a named configuration |
| POST | `/System/Configuration/Partial` | Merge-update server config — **newer servers only, see caveat** |
| GET  | `/System/Configuration/MetadataOptions/Default` | Get a default MetadataOptions object |
| POST | `/System/MediaEncoder/Path` | Update the ffmpeg path (rarely needed; Emby ships its own) |

Version caveat for 4.7.14: `POST /System/Configuration/Partial` (and
`POST /Users/{Id}/Configuration/Partial`) appear in the current (4.8/4.9-era) API reference
but are **not** part of the older API surface (they are absent from the pre-4.x open-source
`ConfigurationService`). Do not assume they exist on 4.7.14 — probe first, and prefer the
full round-trip pattern below, which works on every version.

### The single most important gotcha: full-object round-trip

`POST /System/Configuration`, `POST /System/Configuration/{Key}`, `POST /Users/{Id}/Policy`
and `POST /Users/{Id}/Configuration` **replace the entire object**. Any property you omit is
reset to its .NET default (false/0/null), not left unchanged. The only safe write pattern is:

1. `GET` the current object.
2. Mutate only the fields you intend to change, preserving everything else verbatim.
3. `POST` the whole object back.

This also future-proofs you across versions: fields you don't recognize are round-tripped
untouched. Never construct a config object from scratch.

Source: https://dev.emby.media/reference/RestAPI/ConfigurationService/postSystemConfiguration.html
(and sibling pages under https://dev.emby.media/reference/RestAPI/ConfigurationService.html)

## 4. ServerConfiguration — important keys

Verified against the official OpenAPI spec
(https://github.com/MediaBrowser/Emby.SDK/blob/master/Resources/OpenApi/openapi_v3.json).
The spec tracks the latest release; the core fields below are long-standing, but a few noted
ones are newer than 4.7 — always round-trip, never write fields you didn't read.

Networking / remote access (Dashboard → Network):
- `EnableRemoteAccess` (bool) — master switch for WAN access.
- `HttpServerPortNumber` (default 8096), `HttpsPortNumber` (default 8920).
- `EnableHttps` (bool), `CertificatePath` (PKCS#12 .pfx file), `CertificatePassword`,
  `RequireHttps` (bool — one of the "secure connection mode" behaviors).
- `EnableUPnP` (bool — automatic port mapping), `PublicPort`, `PublicHttpsPort` (WAN ports
  reported to remote clients; may differ from local ports).
- `WanDdns` (string — "External domain"; hostname only, no port).
- `IsBehindProxy` (bool) — with a reverse proxy, trust `X-Real-Ip`/`X-Forwarded-For`
  (newer builds expose `ProxyHeaderMode` instead/in addition).
- `LocalNetworkSubnets` (string[] of CIDRs, e.g. `["192.0.2.0/24"]`) — what counts as LAN
  for bandwidth/access decisions; `LocalNetworkAddresses` — bind addresses.
- `RemoteIPFilter` (string[]) + `IsRemoteIPFilterBlacklist` (bool) — allow/deny lists.
- `RemoteClientBitrateLimit` (int, bits-per-second; 0 = unlimited) — global internet
  streaming cap. `SimultaneousStreamLimit` (int; Premiere feature).

Server / general:
- `ServerName`, `UICulture`, `PreferredMetadataLanguage`, `MetadataCountryCode`.
- `CachePath`, `MetadataPath` (move cache/metadata off the system disk).
- `EnableDebugLevelLogging` (bool), `LogFileRetentionDays` (int).
- `EnableAutomaticRestart`, `EnableAutoUpdate`, `IsStartupWizardCompleted`.

Library / scanning:
- `LibraryMonitorDelaySeconds` (int) — debounce for real-time monitoring.
- `ImageExtractionTimeoutMs` (int) — 0 = no timeout for chapter/thumb extraction.
- `PathSubstitutions` (array of `{From, To}`) — server-path → client-path mapping.

Database tuning (see optimization.md):
- `DatabaseCacheSizeMB`, `EnableSqLiteMmio`, `VacuumDatabaseOnStartup`,
  `OptimizeDatabaseOnShutdown`, `DatabaseAnalysisLimit`, `MaxLibraryDatabaseConnections`.

Safe-values guidance: leave ports at 8096/8920 unless colliding; keep `EnableUPnP=false` and
forward ports manually or use a reverse proxy (per official Connectivity article the UPnP
route is best-effort); never set `RequireHttps=true` before a certificate is configured and
tested, or you can lock clients out; when changing `LocalNetworkSubnets` remember that a
wrong value makes LAN clients count as "remote" and subjects them to remote bitrate limits
and per-user `EnableRemoteAccess` policy.

Sources:
- https://emby.media/support/articles/Hosting-Settings.html (Network settings semantics)
- https://emby.media/support/articles/Connectivity.html (remote access, ports 8096/8920/7359)
- OpenAPI `ServerConfiguration` schema (Emby.SDK repo, link above)

## 5. Named configurations — /System/Configuration/{Key}

Keys registered by the server core (verified in the Emby source):

| Key | Type | File | Contents |
|---|---|---|---|
| `encoding` | EncodingOptions | config/encoding.xml | Transcoding/hardware-accel settings |
| `dlna` | DlnaOptions | config/dlna.xml | DLNA server & Play To |
| `livetv` | LiveTvOptions | config/livetv.xml | Tuners, guide providers, recording paths |
| `notifications` | NotificationOptions | config/notifications.xml | Notification toggles per event |
| `devices` | DevicesOptions | config/devices.xml | Camera upload etc. |
| `branding` | BrandingOptions | config/branding.xml | Login disclaimer, custom CSS |
| `xbmcmetadata` | XbmcMetadataOptions | config/xbmcmetadata.xml | NFO metadata settings |

Plugins register additional keys (e.g. the Auto-Organize plugin uses `autoorganize`).
`GET /System/Configuration/{Key}` returns the object; `POST` with the full modified object
(same round-trip rule). An unknown key returns 404 ("Configuration with key X not found") —
you cannot invent keys.

Do NOT import Jellyfin key names (`network`, `migrations`, etc.) — they do not exist in Emby.

`encoding` (EncodingOptions) — fields verified in the Emby codebase (pre-4.x open source;
still-present core of 4.x, which adds more fields on top — round-trip!):

- `EncodingThreadCount` (int, -1 = Auto — official guidance: leave on Auto)
- `TranscodingTempPath` (string; server appends `transcoding-temp`)
- `DownMixAudioBoost` (double, default 2)
- `EnableThrottling` (bool) / `ThrottleDelaySeconds` (int, default ~180)
- `HardwareAccelerationType` (string)
- `VaapiDevice` (string, default `/dev/dri/renderD128`)
- `H264Crf` (int, default 23), `H264Preset` (string)
- `EnableHardwareEncoding` (bool), `EnableSubtitleExtraction` (bool)
- `HardwareDecodingCodecs` (string[], e.g. `["h264","hevc","mpeg2video","vc1"]`)

In Emby 4.7 the dashboard exposes per-codec hardware decode toggles and tone-mapping options
that map onto additional EncodingOptions fields; because these evolved across 4.x point
releases, treat the GET response of *your* server as the schema of record.

Sources:
- https://dev.emby.media/reference/RestAPI/ConfigurationService.html
- https://github.com/MediaBrowser/Emby/blob/master/Emby.Server.Implementations/Configuration/ServerConfigurationManager.cs
  (`GetConfiguration<EncodingOptions>("encoding")`)
- https://github.com/MediaBrowser/Emby.Common/blob/master/MediaBrowser.Model/Configuration/EncodingOptions.cs
- https://github.com/MediaBrowser/Emby/blob/master/Emby.Dlna/Configuration/DlnaOptions.cs

## 6. User policy and user configuration

Users are managed under `/Users`:

- `GET /Users/Query` (admin list; plain `GET /Users` also works), `GET /Users/{Id}`,
  `POST /Users/New` (`{"Name": "..."}`),
  `DELETE /Users/{Id}`, `POST /Users/{Id}` (rename/update), `POST /Users/{Id}/Password`.
- **Policy** (admin-controlled permissions): `POST /Users/{Id}/Policy` with the FULL
  `UserPolicy` object (read it from `GET /Users/{Id}` → `.Policy` first!). Key fields:
  `IsAdministrator`, `IsDisabled`, `IsHidden`, `EnableRemoteAccess`, `EnableMediaPlayback`,
  `EnableAudioPlaybackTranscoding`, `EnableVideoPlaybackTranscoding`, `EnablePlaybackRemuxing`,
  `EnableContentDeletion`, `EnableContentDownloading`, `EnableSubtitleDownloading`,
  `EnableSyncTranscoding`, `EnableMediaConversion`, `EnableLiveTvAccess`,
  `EnableLiveTvManagement`, `MaxParentalRating` (int), `BlockedTags`/`BlockUnratedItems`,
  `AccessSchedules`, `EnableAllFolders` + `EnabledFolders` (library access by folder Id),
  `EnableAllDevices` + `EnabledDevices`, `RemoteClientBitrateLimit`,
  `SimultaneousStreamLimit`, `InvalidLoginAttemptCount`, `EnablePublicSharing`.
  Gotcha: POSTing a policy with `EnableAllFolders:false` and an empty `EnabledFolders`
  removes all library access; forgetting `IsAdministrator:true` demotes an admin.
- **Configuration** (user preferences): `POST /Users/{Id}/Configuration` with the full
  `UserConfiguration` (from `GET /Users/{Id}` → `.Configuration`): `AudioLanguagePreference`,
  `PlayDefaultAudioTrack`, `SubtitleLanguagePreference`, `SubtitleMode`
  (Default/Always/OnlyForced/None/Smart), `HidePlayedInLatest`, `RememberAudioSelections`,
  `RememberSubtitleSelections`, `EnableNextEpisodeAutoPlay`, etc.
- `POST /Users/{Id}/Configuration/Partial` exists on newer servers only (see §3 caveat).

Source: https://dev.emby.media/reference/RestAPI/UserService.html

## 7. Library configuration (virtual folders + LibraryOptions)

- `GET /Library/VirtualFolders/Query` (or `/Library/VirtualFolders`) — every library with
  `Name`, `ItemId`, `Guid`, `CollectionType`, `Locations[]`, `LibraryOptions`, plus live
  `RefreshProgress`/`RefreshStatus`.
- `POST /Library/VirtualFolders` — create (`?name=&collectionType=&refreshLibrary=` with a
  `LibraryOptions` body); `DELETE /Library/VirtualFolders?name=` — remove.
- `POST /Library/VirtualFolders/Name` — rename.
- `POST /Library/VirtualFolders/Paths` / `.../Paths/Update` / `DELETE .../Paths` — manage folders.
- `POST /Library/VirtualFolders/LibraryOptions` — body `{ "Id": "<library ItemId>",
  "LibraryOptions": { ...full object... } }`. Same round-trip rule: send the complete
  LibraryOptions read from the Query endpoint.

LibraryOptions highlights (4.7-relevant): `EnableRealtimeMonitor`,
`EnableChapterImageExtraction`, `ExtractChapterImagesDuringLibraryScan`,
`DownloadImagesInAdvance`, `SaveLocalMetadata`, `EnableEmbeddedTitles`,
`AutomaticRefreshIntervalDays`, `PreferredMetadataLanguage`, `MetadataCountryCode`,
`MetadataSavers`, `LocalMetadataReaderOrder`, subtitle download options
(`SubtitleDownloadLanguages`, `RequirePerfectSubtitleMatch`, `SaveSubtitlesWithMedia`),
`TypeOptions` (per-type metadata/image fetcher order). Fields such as
`EnableMarkerDetection` (intro detection) and the lyrics options are 4.8+ — they will simply
not appear on a 4.7.14 GET; do not add them.

Sources:
- https://dev.emby.media/reference/RestAPI/LibraryStructureService.html
- https://emby.media/support/articles/Library-Setup.html
- OpenAPI `LibraryOptions` schema (Emby.SDK)

## 8. DLNA and Live TV config areas

- DLNA: named config `dlna` (see table above): `EnableServer` (DLNA server on/off),
  `EnablePlayTo`, `BlastAliveMessages`, `BlastAliveMessageIntervalSeconds` (default 1800),
  `ClientDiscoveryIntervalSeconds` (default 60), `EnableDebugLog`, `DefaultUserId`.
  Custom device profiles are managed via the `/Dlna/Profiles` endpoints and the dashboard
  (https://emby.media/support/articles/Dlna-Profiles.html).
- Live TV: named config `livetv` holds tuner/provider/recording-path settings, but tuners
  and guide providers are normally managed through the dedicated `/LiveTv/*` endpoints
  (TunerHosts, ListingProviders). Live TV+DVR requires Emby Premiere.
  (https://emby.media/support/articles/Live-TV.html)

## 9. Applying changes

- Most config POSTs apply immediately; some networking changes (ports, HTTPS cert) need a
  restart: `POST /System/Restart`. On Linux the restart depends on the
  `/usr/lib/emby-server/restart.sh` helper being intact (see troubleshooting.md).
- Verify current effective state after writing: `GET /System/Info` (admin) includes
  `HttpServerPortNumber`, `SupportsAutoRunAtStartup`, `TranscodingTempPath`, data paths, etc.

## Source index

- REST API home: https://dev.emby.media/doc/restapi/index.html
- API key auth: https://dev.emby.media/doc/restapi/API-Key-Authentication.html
- User auth: https://dev.emby.media/doc/restapi/User-Authentication.html
- ConfigurationService reference: https://dev.emby.media/reference/RestAPI/ConfigurationService.html
- UserService reference: https://dev.emby.media/reference/RestAPI/UserService.html
- LibraryStructureService reference: https://dev.emby.media/reference/RestAPI/LibraryStructureService.html
- Official support articles: https://emby.media/support/articles/{Article}.html — canonical
  markdown source: https://github.com/EmbySupport/Emby.Docs
- OpenAPI spec: https://github.com/MediaBrowser/Emby.SDK/tree/master/Resources/OpenApi
