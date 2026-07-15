---
description: Onboard or reshape an Emby user with sensible presets (kid, guest, standard, admin)
argument-hint: e.g. "add kid account Milo", "make Home a guest", "audit users"
---

# Emby user onboarding & presets

Manage users end-to-end using the `emby` MCP tools. Writes preview → approval
→ confirm.

Presets (starting points — tune with me before applying):

- **kid** — `{"IsAdministrator": false, "MaxParentalRating": 7,
  "EnableContentDeletion": false, "EnableRemoteAccess": false,
  "EnableLiveTvManagement": false, "EnableAllFolders": false,
  "EnabledFolders": [<ids I approve>], "BlockUnratedItems": ["Movie","Series"]}`
  + home screen `{"homesection0": "resume", "homesection1": "latestmedia"}`
  + user config `{"EnableNextEpisodeAutoPlay": false}` (bedtime-friendly)
- **guest** — no admin, no deletion, no remote access, no Live TV management,
  all (or selected) libraries, hidden from login screen optional
  (`"IsHidden": true`).
- **standard** — playback everywhere incl. remote, no admin/deletion/
  management.
- **admin** — `"IsAdministrator": true` (confirm twice — full control).

Flow for "add <preset> account <name>":
1. `emby_create_user(name, confirm=true)` → `emby_set_user_password` if I
   provide one.
2. `emby_libraries()` → pick folder ids if the preset restricts libraries
   (ask me which).
3. `emby_update_user_policy(name, <preset patch>, confirm=true)`.
4. Optional: `emby_display_prefs(name, patch=...)` home screen; per-user
   playback defaults (subtitle/audio language) via user Configuration
   (customization.md §10).
5. Verify with `emby_user(name)` and summarize the final policy.

"audit users" → `emby_users()` table: admin/disabled/remote/deletion/
last-login; flag risky combos (deletion rights on non-admins, remote access
with no password — check `HasPassword`).
