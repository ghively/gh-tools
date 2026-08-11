# Postmortem — shfs reload wiped a running PostgreSQL (romm DB)

Date: 2026-08-11
Plugin: `unraid-control`
Severity: data loss (romm's PostgreSQL database)

## Summary

While live-testing the new share-management tools on the Unraid box GH-Nvidia,
`unraid_share_create`/`_delete` applied share changes via `emcmd changeShare`.
That makes emhttpd "Restart services", which reloads the `/mnt/user` FUSE (shfs)
layer. romm's PostgreSQL container bind-mounts its data directory through a
`/mnt/user/appdata/...` path, so the reload severed the database's open files
mid-operation. PostgreSQL crashed and its data directory was left effectively
empty. No backup or btrfs snapshot of that data existed.

## Timeline (box local time, CDT)

- 01:27:54 — PostgreSQL healthy (normal checkpoints).
- 01:29:16 — `emhttpd: Restarting services...` (a share-settings apply).
- 01:29:25 — PostgreSQL: `FATAL: could not open file "global/pg_filenode.map"`.
- 01:29:40 — second `emhttpd: Restarting services...` (creating `ghtools-testshare`).
- 01:29:45 — PostgreSQL container network torn down (process dead).
- Data dir `/mnt/user/appdata/mediastorm/postgres_data` now 4 KB (empty skeleton).

## Root cause (two-sided)

1. **Trigger (ours):** the share tools reloaded shfs by calling
   `emcmd changeShare=Apply/Delete` as part of a routine create/delete.
2. **Vulnerability (environment):** every container on the box mounts appdata
   via the `/mnt/user` FUSE overlay instead of `/mnt/cache/...`. Unraid best
   practice is to mount appdata from the pool/disk directly precisely because a
   shfs reload breaks open file handles on `/mnt/user`.

The cache btrfs filesystem itself was healthy (zero I/O/corruption errors), so
this was an operational fault, not hardware.

## Fixes applied (in code, this repo)

- `unraid_share_create` / `unraid_share_delete` are now **config-only by
  default** (`apply=False`): they write `/boot/config/shares/<name>.cfg` and the
  directory but never reload shfs. The share activates on Unraid's next
  share-settings refresh.
- `apply=True` is **guarded**: it runs `_assert_shfs_safe()` first and refuses if
  any running container bind-mounts appdata via `/mnt/user` (also refuses if
  mounts can't be verified). So the reload can no longer happen while a
  vulnerable container is running.
- New read-only tool `unraid_shfs_risk_check` lists at-risk containers so the
  hazard is visible before any share/array operation.
- SKILL.md and README document the hazard and the migrate-to-`/mnt/cache`
  remediation.

## Recommended remediation on the box (owner action)

- Migrate every container flagged by `unraid_shfs_risk_check` to mount appdata
  from `/mnt/cache/appdata/...` (or `/mnt/<pool>/...`) instead of
  `/mnt/user/appdata/...`, then recreate them. This removes the vulnerability at
  the source.
- Set up appdata backups (e.g. the CA Appdata Backup plugin) and/or periodic
  `pg_dump` of the romm database — none existed at the time of the incident.

## Recovery for the lost romm database

The ROM *files* on disk are untouched; only the PostgreSQL metadata was lost.
Recovery options (owner decision — not performed automatically):
1. Start a fresh PostgreSQL on an EMPTY data dir (let it initdb), let romm
   recreate its schema, then re-scan the library from disk. Loses accounts,
   collections, play history, and save-state metadata; rebuilds the library.
2. If any older copy of `postgres_data` exists elsewhere, restore from it first.
