---
description: Scaffold, build, and deploy a custom Emby server plugin (C#/.NET)
argument-hint: e.g. "scaffold a plugin that tags 4K content", "add a REST endpoint to my plugin"
---

# Emby plugin development

Develop a custom Emby server plugin using the emby-control skill's
plugin-management.md reference (Part b). Target server: Emby 4.7.x —
compile against `MediaBrowser.Server.Core` 4.7.x.

## Scaffold ("scaffold ...")

1. Ask where the project should live (default: a new folder in the current
   workspace, NOT inside the emby plugin directory).
2. Generate:
   - `<Name>.csproj` — netstandard2.0, `MediaBrowser.Server.Core` 4.7.14
   - `Plugin.cs` — `BasePlugin<PluginConfiguration>` with a FRESH `Guid`
     (generate once, never change), Name, Description
   - `PluginConfiguration.cs` — `BasePluginConfiguration` subclass
   - `ServerEntryPoint.cs` — `IServerEntryPoint` with constructor-injected
     services (`ILogManager`, `ILibraryManager`, `ISessionManager`... pick
     per the plugin's purpose)
   - Optional: `Api.cs` (`IService` + `[Route]` DTOs) for REST endpoints;
     `ScheduledTask.cs` (`IScheduledTask`) for background jobs
3. Emby scans plugin assemblies for known interfaces (automatic discovery) —
   no registration wiring needed.

## Build

`dotnet build -c Release` (verify the .NET SDK is installed first;
`dotnet --version`). The deliverable is the single DLL in
`bin/Release/netstandard2.0/`.

## Deploy to media-host

The plugins folder is `/var/lib/emby/plugins/` ON THE SERVER — there is no
upload API. Options (ask which):
- If SSH/SMB access to media-host exists: copy the DLL there, then
  `chown emby:emby` it.
- Otherwise: hand me the DLL path and copy instructions.
Then restart Emby (`emby_restart_server` — check `emby_sessions` for viewers
first) and verify: `emby_plugins()` lists it; startup errors appear in
`emby_logs("embyserver.txt")` (assembly load failures = SDK version
mismatch).

## Iterate

Rebuild → recopy → restart. Plugin config round-trips via
`emby_plugin_config` once the plugin registers a configuration. New REST
routes appear in `emby_list_endpoints` after restart (the OpenAPI catalog
cache refreshes on server restart — re-fetch with a fresh session or
emby_call GET /openapi.json).
