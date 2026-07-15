---
description: Set up a new RomM library from scratch (folder layout, platforms, first scan, metadata)
argument-hint: (optional) platforms you plan to add, e.g. "snes, ps1, gba"
---

# RomM first-library setup

Walk the user from an empty RomM to a populated, matched library. Their server
auto-detected **structure A**: ROMs live at `library/roms/<platform_slug>/`,
BIOS at `library/bios/<platform_slug>/`.

1. **Current state** — `romm_status`: note `filesystem_platform_dirs` (what
   RomM can see) and enabled metadata sources; `romm_stats` for counts.
2. **Plan platform folders** — for each platform in `$ARGUMENTS` (or ask),
   find the canonical slug with `romm_supported_platforms(search=...)` and
   tell the user the exact folder to create, e.g. Super Nintendo →
   `library/roms/snes/`. Non-standard folder names can be mapped instead with
   `romm_config_platform_binding("add", fs_slug="my-folder", slug="snes",
   confirm=True)`.
3. **BIOS/firmware** — for platforms that need BIOS (PS1/PS2, Saturn,
   Dreamcast, NDS, GBA...), tell the user which files go in
   `library/bios/<slug>/`, or upload directly with
   `romm_firmware_upload(platform_id, file_path, confirm=True)`.
4. **Metadata sources** — `romm_status` shows what's enabled. Hasheous +
   LibretroDB work with no keys (hash matching of known dumps). For richer
   text matching suggest adding IGDB or ScreenScraper credentials to the
   server's environment (docker compose), then restarting.
5. **First scan** — once files are in place:
   `romm_scan(scan_type="quick", confirm=True, wait_seconds=600)` (needs
   username/password in config.local.json — see the romm-control skill).
   Report the returned stats.
6. **Verify & fix** — `romm_stats(include_platform_stats=True)`,
   `romm_roms(matched=False, limit=1)` for the unmatched count. If high,
   hand off to `/romm:romm-match`.
7. **Quality of life** — offer to enable the scheduled rescan or filesystem
   watcher (these are env vars on the server: ENABLE_SCHEDULED_RESCAN,
   ENABLE_RESCAN_ON_FILESYSTEM_CHANGE), create a Favorites collection
   (`romm_collection_create(name="Favorites", is_favorite=True)`), and mint
   invite links for other players (`/romm:romm-users`).
