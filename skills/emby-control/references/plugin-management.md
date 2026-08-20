# PLUGIN-MANAGEMENT.md — Emby Plugins: API Management & Development Primer (Emby 4.7.x, Linux)

> **Live-verified delta for media-host (IMPORTANT):** the official docs describe
> `GET/POST /Plugins/{Id}/Configuration`, but on this server it returns
> **HTTP 500 for ALL 18 installed plugins** — modern Emby-authored plugins do
> not implement the legacy configuration class. The WORKING mechanism is named
> config stores: `GET /web/ConfigurationPages` maps plugins to page names, and
> `GET/POST /System/Configuration/{key}` (key ≈ page name minus `js`/`settings`
> suffix) reads/writes the settings — verified live for `opensubtitles`,
> `webhooks`, `cinemamode`, `dlna`, `fanart`, `musicbrainz`. The
> `emby_plugin_config` tool resolves this automatically (legacy route first,
> then named store).

Part (a): driving Emby's plugin system over REST. Part (b): developing Emby server plugins.
Emby-specific — Emby plugins are NOT compatible with Jellyfin plugins and vice versa (the
projects diverged in 2018; Emby's SDK is the closed-source `MediaBrowser.Server.Core` line).

---

## Part (a) — Managing plugins via the REST API

Auth: admin API key (`X-Emby-Token`). Two services are involved: **PackageService**
(the online catalog / installer) and **PluginService** (what's installed locally).

### Catalog (PackageService)

| Method | Path | Purpose |
|---|---|---|
| GET | `/Packages` | All available catalog packages. Query: `PackageType`, `TargetSystems`, `IsPremium`, `IsAdult` |
| GET | `/Packages/{Name}` | One package by name; `?AssemblyGuid=` disambiguates |
| GET | `/Packages/Updates` | Available updates for installed packages |
| POST | `/Packages/Installed/{Name}` | **Install** a package. Query: `AssemblyGuid`, `Version` (omit = latest), `UpdateClass` (`Release`/`Beta`/`Dev`) |
| DELETE | `/Packages/Installing/{Id}` | Cancel an in-flight installation (Id from InstallationInfo) |

`PackageInfo` fields: `name`, `guid`, `overview`, `shortDescription`, `category`,
`targetFilename` (the DLL name), `owner`, `versions[]` (each with version string and
`classification` Release/Beta/Dev), `isPremium` (Premiere-gated), `adult`.
(media-host's catalog exposes 133 packages.)

Install flow:
1. `GET /Packages` → find package, note `name` + `guid`.
2. `POST /Packages/Installed/{name}?AssemblyGuid={guid}&UpdateClass=Release`
3. Installation progress events appear in the Activity Log; the official Plugins article:
   "After the installation has completed, the server will need to be restarted" →
   `POST /System/Restart`.

### Installed plugins (PluginService)

| Method | Path | Purpose |
|---|---|---|
| GET | `/Plugins` | Installed plugins: `Id` (GUID), `Name`, `Version`, `Description`, `ConfigurationFileName`, `ImageTag` |
| DELETE | `/Plugins/{Id}` | Uninstall (alt: `POST /Plugins/{Id}/Delete`) |
| GET | `/Plugins/{Id}/Configuration` | Plugin's configuration object — **500s on modern plugins; see delta box above** |
| POST | `/Plugins/{Id}/Configuration` | Replace plugin configuration — same **full-object round-trip rule** as server config |
| GET | `/Plugins/{Id}/Thumb` | Plugin thumbnail image (500 when the plugin ships none) |

Plugin configuration objects are plugin-defined (each plugin's `BasePluginConfiguration`
subclass); persisted as XML at `<data>/plugins/configurations/{ConfigurationFileName}`
(e.g. `/var/lib/emby/plugins/configurations/Trakt.xml`). Always GET before POST — schema
discovery is per-plugin. Uninstall also usually requires a restart to fully unload the DLL.

### Manual installation (Linux)

For betas or catalog-absent plugins (official Plugins article):
1. Stop Emby Server ("Ensure that Emby Server is shut down when updating plugins").
2. Copy the plugin DLL into **`/var/lib/emby/plugins/`** (when replacing, rename the old
   DLL to `.old` first).
3. Fix ownership/permissions to match the other plugin files (`chown emby:emby`).
4. Start the server.

### Notable plugins (official catalog / MediaBrowser GitHub org)

- **Trakt** — scrobbling/sync (official docs name it a popular choice).
- **Cover Art**, **Trailers**, **GameBrowser** — named in the official Plugins article.
- **Auto Organize** (`Emby.AutoOrganize`, github.com/MediaBrowser/Emby.AutoOrganize) —
  watch-folder file organizing (was core, now a plugin).
- **Fanart** (github.com/MediaBrowser/Fanart.tv) and **NfoMetadata**
  (github.com/MediaBrowser/NfoMetadata) — metadata/image providers.
- **Open Subtitles** — subtitle downloads (configured with OpenSubtitles.com account).
- **Addic7ed** (github.com/MediaBrowser/Addic7ed) — subtitles.
- **Backup** ("Server Configuration Backup") — official settings backup/restore
  (https://emby.media/support/articles/Backup.html).
- **Live TV sources**: NextPVR, VBox, Hauppauge integrations
  (https://emby.media/support/articles/Live-TV-Plugins.html).
- Anime metadata: **MyAnimeList**, **AniList** (MediaBrowser org repos).
- Catalog categories per the official article: Channels, Content Providers, Live TV,
  Metadata, Notifications, Social Integration.

Installed on media-host (2026-07): Bluray Folder Support, Cinema Intros, DLNA, Dvd Folder
Support, Emby Guide Data, Fanart.tv, M3U TV Tuner, MovieDb, MusicBrainz, Nfo Metadata,
OMDb, Open Subtitles, Port Mapper, Studio Images, TheAudioDb, TheTVDB, Webhooks, XmlTV.

Sources:
- https://dev.emby.media/reference/RestAPI/PackageService.html
- https://dev.emby.media/reference/RestAPI/PluginService.html
- https://emby.media/support/articles/Plugins.html
- https://github.com/orgs/MediaBrowser/repositories (official plugin sources)

---

## Part (b) — Developing Emby server plugins (primer)

### Toolchain and packaging model

- Language/framework: **C# class library targeting .NET Standard 2.0** (runs on Emby's
  .NET Core/Mono hosts). IDE: Visual Studio 2017+ (or `dotnet` CLI) with the .NET Core SDK.
- NuGet: reference **`MediaBrowser.Server.Core`** ("core components required to build
  plugins for Emby Server"; depends on `MediaBrowser.Common`). Match the package version to
  your target server — for a 4.7.x server use a 4.7.x package version (packages exist per
  server release; latest is 4.9.x): https://www.nuget.org/packages/MediaBrowser.Server.Core
- A plugin **is just the compiled DLL** dropped into the server's plugins folder —
  on Linux **`/var/lib/emby/plugins/`** — followed by a server restart. No manifest files,
  no zip packaging (Emby ≠ Jellyfin here).

Minimal csproj (from the official wiki):

```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFrameworks>netstandard2.0;</TargetFrameworks>
    <AssemblyVersion>1.0.0.0</AssemblyVersion>
    <FileVersion>1.0.0.0</FileVersion>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="mediabrowser.server.core" Version="4.7.14" />
  </ItemGroup>
</Project>
```

### Core types

- **`MediaBrowser.Model.Plugins.BasePluginConfiguration`** — subclass it to define your
  settings object (this is exactly what the plugin-configuration endpoints serialize).
- **`MediaBrowser.Common.Plugins.BasePlugin<TConfiguration>`** — the plugin main class:

```csharp
public class Plugin : BasePlugin<PluginConfiguration>
{
    public Plugin(IApplicationPaths applicationPaths, IXmlSerializer xmlSerializer)
        : base(applicationPaths, xmlSerializer) { }

    public override Guid Id => new Guid("....-....");  // permanent identity — never change
    public override string Name => "My Plugin";
    public override string Description => "...";
}
```

- **`IServerEntryPoint`** — implement for startup logic (`Run()` on server start,
  `Dispose()` on shutdown). Instances are created by **automatic type discovery**: Emby
  scans plugin assemblies for known interfaces and instantiates them with **constructor
  dependency injection** — request server services as constructor parameters
  (`ILogger`/`ILogManager`, `IFileSystem`, `IHttpClient`, `ILibraryManager`,
  `ISessionManager`, `IServerConfigurationManager`, `INetworkManager`, `IZipClient`, ...).
  `IRequiresRegistration` exists for early registrations.
- Other discoverable extension interfaces include `IScheduledTask` (adds entries to
  Scheduled Tasks — e.g. how Trakt schedules syncs), metadata providers, channels,
  notification services, etc.

### Adding REST endpoints from a plugin

Define request DTOs with routing attributes and a service implementing
`MediaBrowser.Model.Services.IService`; methods are matched by HTTP-verb name:

```csharp
[Route("/Weather", "GET", Description = "Gets weather info")]
public class GetWeather : IReturn<WeatherInfo>
{
    public string Location { get; set; }
}

public class WeatherService : IService
{
    public object Get(GetWeather request) => GetWeatherInfo(request.Location);
}
```

Return serializable objects, strings, byte[] or Streams; implement `IHasResultFactory` for
custom headers/content types/static file results. Endpoints appear under the same base URL
and auth model as the core API.

### Configuration pages / plugin UI

Two generations:
1. Classic: embed HTML/JS pages in the DLL and expose them via `IHasWebPages` /
   plugin configuration pages (the pattern in the legacy wiki and most existing plugins).
2. Modern (documented at dev.emby.media): a **declarative UI** system — you write a
   ViewModel class and the server auto-generates the settings page from its properties
   (string → textbox, bool → checkbox, enum → dropdown) with attributes like
   `[DisplayName]`, `[Description]`, `[Required]`, `[EditFolderPicker]`. Start from the
   official templates.

### Official templates and samples

`github.com/MediaBrowser/Emby.SDK` → `SampleCode/`:
- `Templates/EmbyPluginMinimalTemplate` — barebones plugin
- `Templates/EmbyPluginSimpleUiTemplate` — plugin with a simple settings page
- `Templates/EmbyPluginUiTemplate` — full UI plugin
- `Examples/`, `RestApi/` — API client samples (C#, Java, TypeScript, Python, Swift, Go)
- `Resources/OpenApi/openapi_v3.json` — the full OpenAPI description of the server API

### Build → deploy → debug loop (official guidance)

1. Post-build copy of the DLL into the server's plugins folder (Windows dev example from the
   docs: `copy $(TargetPath) %AppData%\Emby-Server\programdata\plugins\`; on a Linux target
   copy to `/var/lib/emby/plugins/` and `chown emby:emby`).
2. Restart Emby Server; the plugin appears under Dashboard → Plugins.
3. Debugging: create a VS debug profile launching the Emby Server executable
   (`-nointerface` disables the tray UI); or attach to the running process. For fast
   iteration without a debugger: rebuild + restart server.
4. Distribution: plugins are submitted to the official catalog via the Emby team
   (see the Development Policy / plugin catalog submission notes in the dev docs; the
   community "Developer API" forum, https://emby.media/community/forum/47-developer-api/,
   is the primary support channel — Emby staff, e.g. Luke, respond there).

### Version compatibility notes (4.7.x)

- Compile against the 4.7.x `MediaBrowser.Server.Core` package; plugins built against
  newer SDKs may reference APIs that don't exist on 4.7 and will fail to load (check
  embyserver.txt at startup for assembly load errors).
- The catalog automatically serves plugin versions compatible with the server's own
  version/update level; manual installs bypass that safety.

## Source index

- Plugin dev guide: https://dev.emby.media/doc/plugins/dev/index.html
- Creating API endpoints: https://dev.emby.media/doc/plugins/dev/Creating-Api-Endpoints.html
- Plugin UI system: https://dev.emby.media/doc/plugins/ui/index.html
- Legacy step-by-step wiki: https://github.com/MediaBrowser/Emby/wiki/How-to-build-a-Server-Plugin
- SDK repo (templates, OpenAPI, clients): https://github.com/MediaBrowser/Emby.SDK
- NuGet: https://www.nuget.org/packages/MediaBrowser.Server.Core
- Managing plugins (user docs): https://emby.media/support/articles/Plugins.html
- PackageService / PluginService reference:
  https://dev.emby.media/reference/RestAPI/PackageService.html,
  https://dev.emby.media/reference/RestAPI/PluginService.html
