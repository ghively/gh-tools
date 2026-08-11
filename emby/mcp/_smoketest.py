#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["mcp>=1.4.0,<2.0.0", "httpx>=0.27"]
# ///
"""Live smoke test: exercise every read tool for real, and call every write
tool WITHOUT confirm to prove the confirmation gate blocks it. No mutations.
Prints a compact PASS/FAIL line per tool."""
import os
import sys
from pathlib import Path

os.environ.setdefault("EMBY_CONFIG", str(Path(__file__).resolve().parent.parent / "config.local.json"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import emby_server as E  # noqa: E402

FAILS = []


def show(name, res, expect_gate=False):
    ok = False
    hint = ""
    if isinstance(res, dict) and "error" in res:
        hint = str(res["error"])[:80]
    elif expect_gate:
        ok = isinstance(res, dict) and res.get("confirmation_required") is True
        hint = "gate held" if ok else f"GATE MISSING: {str(res)[:80]}"
    else:
        ok = True
        if isinstance(res, dict):
            hint = f"keys={list(res)[:5]}"
        elif isinstance(res, list):
            hint = f"list[{len(res)}]"
        else:
            hint = str(res)[:60]
    print(f"{'PASS' if ok else 'FAIL'}  {name:38} {hint}")
    if not ok:
        FAILS.append(name)


# ---- reads ------------------------------------------------------------- #
st = E.emby_status()
show("emby_status", st)
show("emby_get_config()", E.emby_get_config())
show("emby_get_config(encoding)", E.emby_get_config("encoding"))
logs = E.emby_logs()
show("emby_logs()", logs)
show("emby_logs(embyserver.txt)", E.emby_logs("embyserver.txt", 400))
show("emby_activity", E.emby_activity(5))
tasks = E.emby_scheduled_tasks()
show("emby_scheduled_tasks", tasks)
show("emby_devices", E.emby_devices())
users = E.emby_users()
show("emby_users", users)
uname = users[0]["Name"] if isinstance(users, list) and users else ""
show("emby_user(first)", E.emby_user(uname))
show("emby_libraries", E.emby_libraries())
sr = E.emby_search("the", limit=3)
show("emby_search", sr)
mv = E.emby_items(include_types="Movie", limit=3, sort_by="DateCreated",
                  sort_order="Descending", fields="Path,Genres")
show("emby_items(movies)", mv)
item_id = ""
if isinstance(mv, dict) and mv.get("Items"):
    item_id = mv["Items"][0]["Id"]
    show("emby_item(detail)", E.emby_item(item_id))
    show("emby_playback_info", E.emby_playback_info(item_id))
show("emby_next_up", E.emby_next_up(5))
show("emby_sessions", E.emby_sessions())
plugins = E.emby_plugins()
show("emby_plugins", plugins)
show("emby_packages(trakt)", E.emby_packages("trakt"))
show("emby_plugin_config(list pages)", E.emby_plugin_config())
show("emby_plugin_config(Open Subtitles)", E.emby_plugin_config("Open Subtitles"))
show("emby_plugin_config(webhooks key)", E.emby_plugin_config("webhooks"))
show("emby_plugin_config(DLNA name)", E.emby_plugin_config("DLNA"))
col = E.emby_collection("list")
show("emby_collection(list)", col)
if isinstance(col, dict) and col.get("Items"):
    show("emby_collection(items)", E.emby_collection("items", collection_id=col["Items"][0]["Id"]))
show("emby_playlist(list)", E.emby_playlist("list"))
if item_id:
    show("emby_identify(providers)", E.emby_identify(item_id, "providers"))
    show("emby_identify(search)", E.emby_identify(item_id, "search"))
    show("emby_images(list)", E.emby_images(item_id, "list"))
    show("emby_images(providers)", E.emby_images(item_id, "providers"))
    show("emby_images(search)", E.emby_images(item_id, "search", limit=3))
    show("emby_subtitles(list)", E.emby_subtitles(item_id, "list"))
    show("emby_subtitles(search)", E.emby_subtitles(item_id, "search"))
show("emby_library_manage(get_options)", E.emby_library_manage("get_options", name="Movies"))
show("emby_versions(find_duplicates)", E.emby_versions("find_duplicates", scan_limit=600))
if item_id:
    show("emby_versions(list)", E.emby_versions("list", item_ids=item_id))
show("emby_sync_jobs(targets)", E.emby_sync_jobs("targets"))
show("emby_sync_jobs(jobs)", E.emby_sync_jobs("jobs"))
show("emby_items(missing eps)", E.emby_items(include_types="Episode", is_missing="true", limit=3))
if isinstance(col, dict) and col.get("Items"):
    cid = col["Items"][0]["Id"]
    cmembers = E.emby_collection("items", collection_id=cid)
    show("emby_collection(for_item)", E.emby_collection(
        "for_item", item_ids=cmembers["Items"][0]["Id"])
        if isinstance(cmembers, dict) and cmembers.get("Items") else cmembers)
show("emby_collection(find_franchises)", E.emby_collection("find_franchises"))
show("emby_bulk_update(preview)", E.emby_bulk_update(
    '{"Tags": ["smoke"]}', include_types="Movie", years="1901", limit=5))
show("emby_display_prefs(read)", E.emby_display_prefs())
show("emby_task_triggers(read)", E.emby_task_triggers(
    tasks[0]["Id"] if isinstance(tasks, list) and tasks else "x"))
show("emby_livetv_status", E.emby_livetv_status())
show("emby_livetv_tuner(list)", E.emby_livetv_tuner("list"))
show("emby_livetv_guide_provider(list)", E.emby_livetv_guide_provider("list"))
show("emby_livetv_guide_provider(avail)", E.emby_livetv_guide_provider("available"))
show("emby_livetv_channels", E.emby_livetv_channels(limit=3))
show("emby_livetv_guide", E.emby_livetv_guide(hours=2, limit=3))
show("emby_livetv_dvr(recordings)", E.emby_livetv_dvr("recordings"))
show("emby_livetv_dvr(timers)", E.emby_livetv_dvr("timers"))
show("emby_list_endpoints(tags)", E.emby_list_endpoints(tag="?"))
show("emby_list_endpoints(subtitle)", E.emby_list_endpoints("subtitle", limit=5))
show("emby_call(GET public info)", E.emby_call("GET", "/System/Info/Public"))
show("emby_call(params)", E.emby_call("GET", "/Items", params='{"IncludeItemTypes":"Movie","Recursive":true,"Limit":1}'))

# ---- write gates (must all hold WITHOUT confirm; nothing mutated) ------- #
task_id = tasks[0]["Id"] if isinstance(tasks, list) and tasks else "x"
plug_id = plugins[0]["Id"] if isinstance(plugins, list) and plugins else "x"
iid = item_id or "x"
show("gate emby_set_config", E.emby_set_config('{"EnableUPnP": true}'), expect_gate=True)
show("gate emby_restart_server", E.emby_restart_server(), expect_gate=True)
show("gate emby_shutdown_server", E.emby_shutdown_server(), expect_gate=True)
show("gate emby_run_task", E.emby_run_task(task_id), expect_gate=True)
show("gate emby_update_user_policy", E.emby_update_user_policy(uname, '{"IsHidden": false}'), expect_gate=True)
show("gate emby_create_user", E.emby_create_user("smoketest"), expect_gate=True)
show("gate emby_delete_user", E.emby_delete_user(uname), expect_gate=True)
show("gate emby_set_user_password", E.emby_set_user_password(uname, "x"), expect_gate=True)
show("gate emby_scan_library", E.emby_scan_library(), expect_gate=True)
show("gate emby_update_item", E.emby_update_item(iid, '{"Tags": []}'), expect_gate=True)
show("gate emby_refresh_item", E.emby_refresh_item(iid), expect_gate=True)
show("gate emby_delete_item", E.emby_delete_item(iid), expect_gate=True)
show("gate emby_playback_control", E.emby_playback_control("s", "Pause"), expect_gate=True)
show("gate emby_play", E.emby_play("s", iid), expect_gate=True)
show("gate emby_send_message", E.emby_send_message("s", "hi"), expect_gate=True)
show("gate emby_send_command", E.emby_send_command("s", "Mute"), expect_gate=True)
show("gate emby_install_plugin", E.emby_install_plugin("Trakt"), expect_gate=True)
show("gate emby_uninstall_plugin", E.emby_uninstall_plugin(plug_id), expect_gate=True)
show("gate emby_plugin_config(write)", E.emby_plugin_config("webhooks", '{"Events": []}'), expect_gate=True)
show("gate emby_collection(create)", E.emby_collection("create", name="smoke"), expect_gate=True)
show("gate emby_playlist(create)", E.emby_playlist("create", name="smoke"), expect_gate=True)
show("gate emby_livetv_tuner(add)", E.emby_livetv_tuner("add", url="http://x/pl.m3u"), expect_gate=True)
show("gate emby_livetv_tuner(delete)", E.emby_livetv_tuner("delete", tuner_id="x"), expect_gate=True)
show("gate emby_livetv_provider(add)", E.emby_livetv_guide_provider("add", path="http://x/g.xml"), expect_gate=True)
show("gate emby_livetv_provider(del)", E.emby_livetv_guide_provider("delete", provider_id="x"), expect_gate=True)
show("gate emby_livetv_dvr(cancel)", E.emby_livetv_dvr("cancel", timer_id="x"), expect_gate=True)
show("gate emby_identify(apply)", E.emby_identify(iid, "apply", result_json='{"Name": "X"}'), expect_gate=True)
show("gate emby_images(download)", E.emby_images(iid, "download", url="http://x/i.jpg"), expect_gate=True)
show("gate emby_images(delete)", E.emby_images(iid, "delete"), expect_gate=True)
show("gate emby_subtitles(download)", E.emby_subtitles(iid, "download", subtitle_id="x"), expect_gate=True)
show("gate emby_subtitles(delete)", E.emby_subtitles(iid, "delete", index=0), expect_gate=True)
show("gate emby_library_manage(create)", E.emby_library_manage("create", name="smoke"), expect_gate=True)
show("gate emby_library_manage(delete)", E.emby_library_manage("delete", name="Movies"), expect_gate=True)
show("gate emby_library_manage(options)", E.emby_library_manage("update_options", name="Movies", options_patch='{"EnableRealtimeMonitor": true}'), expect_gate=True)
show("gate emby_bulk_update", E.emby_bulk_update('{"Tags": ["x"]}', include_types="Movie", years="1901", limit=2), expect_gate=True)
show("gate emby_versions(merge)", E.emby_versions("merge", item_ids=f"{iid},{iid}"), expect_gate=True)
show("gate emby_versions(split)", E.emby_versions("split", item_ids=iid), expect_gate=True)
show("gate emby_sync_jobs(create)", E.emby_sync_jobs("create", target_id="originalmediafolder", item_ids=iid), expect_gate=True)
show("gate emby_sync_jobs(cancel)", E.emby_sync_jobs("cancel", job_id="999"), expect_gate=True)
if isinstance(col, dict) and col.get("Items"):
    show("gate emby_collection(sync_query)", E.emby_collection(
        "sync_query", collection_id=col["Items"][0]["Id"], genres="Horror"), expect_gate=True)
show("gate emby_collection(create+query)", E.emby_collection("create", name="smoke", genres="Horror"), expect_gate=True)
show("gate emby_display_prefs(write)", E.emby_display_prefs(patch='{"homesection0": "resume"}'), expect_gate=True)
show("gate emby_task_triggers(write)", E.emby_task_triggers(task_id, '[]'), expect_gate=True)
show("gate emby_set_userdata", E.emby_set_userdata(iid, played="true"), expect_gate=True)

# validation-only (no flags -> friendly error, no mutation)
res = E.emby_set_userdata("x")
ok = isinstance(res, dict) and "Nothing to do" in str(res.get("error", ""))
print(f"{'PASS' if ok else 'FAIL'}  {'emby_set_userdata(validation)':38} {str(res)[:70]}")
if not ok:
    FAILS.append("emby_set_userdata")

print()
if FAILS:
    print(f"FAILURES ({len(FAILS)}): {', '.join(FAILS)}")
    sys.exit(1)
print("ALL PASS")
