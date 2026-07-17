#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["mcp>=1.4.0", "httpx>=0.27", "python-socketio[client]>=5.11"]
# ///
"""Live smoke test for the RomM MCP server: exercise every read tool for
real against the configured server, and call every write tool WITHOUT
confirm to prove the confirmation gate blocks it. No mutations.
Prints a compact PASS/FAIL line per tool."""
import os
import sys
from pathlib import Path

# RomM log/scan output contains emoji; Windows consoles default to cp1252.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

os.environ.setdefault(
    "ROMM_CONFIG",
    str(Path(__file__).resolve().parent.parent / "config.local.json"),
)
sys.path.insert(0, str(Path(__file__).resolve().parent))
import romm_server as R  # noqa: E402

FAILS = []


def show(name, res, expect_gate=False, allow_error_substr=""):
    text = str(res)
    is_err = text.startswith("ERROR:")
    if expect_gate:
        ok = "CONFIRMATION REQUIRED" in text
        hint = "gate held" if ok else f"GATE MISSING: {text[:90]}"
    elif allow_error_substr:
        ok = allow_error_substr.lower() in text.lower()
        hint = text[:90]
    else:
        ok = not is_err
        hint = text[:90].replace("\n", " ")
    print(f"{'PASS' if ok else 'FAIL'}  {name:36} {hint}")
    if not ok:
        FAILS.append(name)


# ---- generic layer ----
show("romm_endpoints(search=scan)", R.romm_endpoints(search="scan"))
show("romm_endpoints(tag=roms)", R.romm_endpoints(tag="roms"))
show("romm_schema(/api/roms get)", R.romm_schema("/api/roms", "get"))
show("romm_call GET /api/heartbeat", R.romm_call("GET", "/api/heartbeat"))
show("romm_call write gate", R.romm_call("POST", "/api/platforms"), expect_gate=True)

# ---- system ----
show("romm_status", R.romm_status())
show("romm_stats", R.romm_stats())
show("romm_stats(platform)", R.romm_stats(include_platform_stats=True))
show("romm_logs", R.romm_logs(limit=5))
show("romm_tasks", R.romm_tasks())
show("romm_config", R.romm_config())

# ---- platforms ----
show("romm_platforms", R.romm_platforms())
show("romm_supported_platforms(n64)", R.romm_supported_platforms("nintendo 64"))

# ---- roms ----
show("romm_roms(limit=5)", R.romm_roms(limit=5))
show("romm_roms(search)", R.romm_roms(search_term="mario", limit=5))

# ---- collections ----
show("romm_collections(all)", R.romm_collections())  # now includes real virtual data, not a note

# ---- users / permissions / keys ----
show("romm_users", R.romm_users())
show("romm_user(1)", R.romm_user(1))
show("romm_permissions(me)", R.romm_permissions("me"))
show("romm_permissions(catalog)", R.romm_permissions("catalog"))
show("romm_permissions(groups)", R.romm_permissions("groups"))
show("romm_api_keys(list)", R.romm_api_keys("list"))
show("romm_api_keys(list_all)", R.romm_api_keys("list_all"))

# ---- assets ----
show("romm_saves", R.romm_saves())
show("romm_states", R.romm_states())
show("romm_firmware", R.romm_firmware())

# ---- devices / activity / music / feeds ----
show("romm_devices", R.romm_devices())
show("romm_activity", R.romm_activity())
show("romm_play_sessions", R.romm_play_sessions(limit=5))
show("romm_music(albums)", R.romm_music("albums", limit=5))
show("romm_feeds()", R.romm_feeds())
show("romm_feeds(webrcade)", R.romm_feeds("webrcade"))

# ---- device pairing / sync / netplay (new) ----
show("romm_sync(sessions)", R.romm_sync("sessions"))
show(
    "romm_device_auth(pending, unknown code)",
    R.romm_device_auth("pending", user_code="smoketest-unknown-code"),
    allow_error_substr="404",
)
show(
    "romm_netplay_rooms(unknown game)",
    R.romm_netplay_rooms(game_id="smoketest-unknown-game"),
)

# ---- confirmation gates on every write tool (no mutations happen) ----
show("gate platform_create", R.romm_platform_create("snes"), expect_gate=True)
show("gate platform_update", R.romm_platform_update(1, "{}"), expect_gate=True)
show("gate platform_delete", R.romm_platform_delete(1), expect_gate=True)
show("gate rom_update", R.romm_rom_update(1), expect_gate=True)
show("gate rom_delete", R.romm_rom_delete([1]), expect_gate=True)
show("gate rom_note_delete", R.romm_rom_notes(1, "delete", note_id=1), expect_gate=True)
show("gate task_run", R.romm_task_run("cleanup_orphaned_resources"), expect_gate=True)
show("gate config_exclude", R.romm_config_exclude("add", "EXCLUDED_SINGLE_EXT", "tmp"), expect_gate=True)
show("gate config_binding", R.romm_config_platform_binding("add", "x", "y"), expect_gate=True)
show("gate collection_update", R.romm_collection_update(1), expect_gate=True)
show("gate collection_delete", R.romm_collection_delete(1), expect_gate=True)
show("gate user_create", R.romm_user_create("x", "x@x", "pw"), expect_gate=True)
show("gate user_update", R.romm_user_update(1, "{}"), expect_gate=True)
show("gate user_delete", R.romm_user_delete(1), expect_gate=True)
show("gate user_invite", R.romm_user_invite(), expect_gate=True)
show("gate api_key_create", R.romm_api_keys("create", name="x", scopes=["me.read"]), expect_gate=True)
show("gate api_key_revoke", R.romm_api_keys("revoke", token_id=1), expect_gate=True)
show("gate saves_delete", R.romm_saves_delete([1]), expect_gate=True)
show("gate states_delete", R.romm_states_delete([1]), expect_gate=True)
show("gate firmware_upload", R.romm_firmware_upload(1, "x"), expect_gate=True)
show("gate firmware_delete", R.romm_firmware_delete([1]), expect_gate=True)
show("gate device_delete", R.romm_device_delete(1), expect_gate=True)
show("gate device_update", R.romm_device_update("x", "{}"), expect_gate=True)
show("gate upload_rom", R.romm_upload_rom(1, "x"), expect_gate=True)
show("gate export(local)", R.romm_export("pegasus", [1], local_export=True), expect_gate=True)
show("gate rom_manuals(redownload)", R.romm_rom_manuals(1, "redownload"), expect_gate=True)
show("gate rom_manuals(delete_all)", R.romm_rom_manuals(1, "delete_all"), expect_gate=True)
show("gate rom_manuals(delete_file)", R.romm_rom_manuals(1, "delete_file", file_id=1), expect_gate=True)
show("gate rom_soundtracks(delete)", R.romm_rom_soundtracks(1, "delete", file_id=1), expect_gate=True)
show("gate rom_patch", R.romm_rom_patch(1, patch_file_id=1), expect_gate=True)
show("gate rom_convert_to_folder", R.romm_rom_convert_to_folder(1), expect_gate=True)
show("gate screenshot(delete)", R.romm_screenshot("delete", screenshot_id=1), expect_gate=True)
show("gate smart_collection_update", R.romm_smart_collection_update(1), expect_gate=True)
show("gate permission_group(update)", R.romm_permission_group("update", group_id=1, name="x"), expect_gate=True)
show("gate permission_group(delete)", R.romm_permission_group("delete", group_id=1), expect_gate=True)
show("gate user_permissions_update", R.romm_user_permissions_update(1), expect_gate=True)
show(
    "gate permission_hidden",
    R.romm_permission_hidden("add", "roms", 1, user_id=1),
    expect_gate=True,
)
show(
    "gate device_auth(approve)",
    R.romm_device_auth("approve", user_code="x", approved_scopes=["me.read"]),
    expect_gate=True,
)
show("gate device_auth(deny)", R.romm_device_auth("deny", user_code="x"), expect_gate=True)
show("gate sync(trigger)", R.romm_sync("trigger", device_id="x"), expect_gate=True)
show("gate scan", R.romm_scan(), expect_gate=True)
show(
    "scan_status(none running) clear error",
    R.romm_scan_status(wait_seconds=0),
    allow_error_substr="no scan is currently running",
)

# Without creds, scan+confirm must fail with a clear message, not hang.
# With creds configured we do NOT fire a real scan from a smoke test.
if not (R.USERNAME and R.PASSWORD):
    show(
        "scan(no creds) clear error",
        R.romm_scan(confirm=True),
        allow_error_substr="username+password",
    )
else:
    print("SKIP  scan live-trigger (creds configured; verified separately)")

print()
if FAILS:
    print(f"{len(FAILS)} FAILURES: {FAILS}")
    sys.exit(1)
print("ALL PASS")
