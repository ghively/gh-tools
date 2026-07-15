---
description: Audit the ROM library — unmatched games, duplicates, missing files, per-platform breakdown
argument-hint: (optional) a platform name/slug to focus on
---

# RomM library audit

Audit the ROM library for quality and completeness using the `romm` MCP tools.
This is **read-only** — report findings; only act if the user asks afterwards.

If `$ARGUMENTS` names a platform, resolve it with `romm_platforms` first and
scope every query below with its `platform_id`.

1. **Shape** — `romm_stats(include_platform_stats=True)` + `romm_platforms`:
   per-platform ROM counts, total size.
2. **Unmatched** — `romm_roms(matched=False, limit=50)`: games with no
   metadata identity. For each (up to ~20), note the filename — obvious causes
   are bad platform folder, renamed files, or hacks/homebrew no provider knows.
3. **Missing from disk** — `romm_roms(missing=True, limit=50)`: DB entries whose
   files vanished (moved/deleted outside RomM). These are candidates for
   `romm_task_run("cleanup_missing_roms")`.
4. **Duplicates** — `romm_roms(duplicate=True, limit=50)`: same game present
   multiple times; group by name and list the file variants.
5. **Unverified dumps (optional)** — `romm_roms(verified=False, limit=1)` total
   as a data point (hash-verification needs Hasheous/RA matches).
6. **Firmware coverage** — `romm_firmware()`: platforms that typically need
   BIOS files (PS1/PS2, Saturn, Dreamcast, GBA, NDS...) but have none.

## Output

A compact report: per-platform table (name, ROMs, size), then findings ordered
by impact (unmatched → missing → duplicates → firmware gaps), each with the
concrete next action and the exact tool call that would perform it. Ask before
running any fix.
