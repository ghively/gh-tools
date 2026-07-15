---
description: Manage Emby plugins — browse catalog, install, configure, remove
argument-hint: e.g. "search trakt", "install Trakt", "configure Open Subtitles"
---

# Emby plugin management

Manage server plugins using the `emby` MCP tools. Writes are confirm-gated.

Parse `$ARGUMENTS`:

- **"search X" / browse** → `emby_packages(search)`; show name, description,
  category, premium flag, installed version. No args → `emby_plugins()`
  (installed) plus notable catalog highlights.
- **"install X"** → find the exact package name via `emby_packages`, preview
  with the user, `emby_install_plugin(name, confirm=true)`, watch
  `emby_activity` for completion, then remind that a server restart is needed
  (offer the /emby-maintenance restart flow — check viewers first).
- **"configure X"** → `emby_plugin_config(X)` to read current settings (it
  auto-resolves Emby 4.x named config stores; empty arg lists all config
  pages). Show settings, apply requested changes with
  `emby_plugin_config(X, patch, confirm=true)`, then re-read to verify.
- **"remove/uninstall X"** → match in `emby_plugins()`, preview,
  `emby_uninstall_plugin(id, confirm=true)`, remind about restart.

Note: plugin settings may contain credentials (e.g. Open Subtitles account) —
never echo passwords/keys back in full; mask all but the first characters.
