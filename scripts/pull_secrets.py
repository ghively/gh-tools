#!/usr/bin/env python3
"""Build every plugin's git-ignored config.local.json from 1Password.

Requires an active `op` session in this shell:
    eval $(op signin) && python3 scripts/pull_secrets.py [--dry-run] [--vault Gregory]

For each plugin it copies config.example.json (minus the _comment), then fills
the secret fields from the best-matching item in the vault. Matching is by
item-title keyword; field extraction prefers explicit labels (api key, token)
then falls back to the item's password/username purposes. Plugins with no
match are reported and skipped — nothing half-written. Files are chmod 0600.

Run with --dry-run first to see the item mapping without writing anything.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# plugin dir -> (title keywords, {config_key: field-label hints})
SERVICES: dict[str, tuple[list[str], dict[str, list[str]]]] = {
    "radarr-control": (["radarr"], {"api_key": ["api key", "credential", "password"]}),
    "sonarr-control": (["sonarr"], {"api_key": ["api key", "credential", "password"]}),
    "sabnzbd-control": (["sabnzbd"], {"api_key": ["api key", "credential", "password"]}),
    "emby": (["emby"], {"api_key": ["api key", "credential", "password"]}),
    "gitlab": (["gitlab"], {"token": ["token", "credential", "password"]}),
    "romm": (["romm"], {"api_key": ["api key"], "username": ["username"], "password": ["password"]}),
    "romarr": (["romarr"], {"api_key": ["api key", "credential", "password"]}),
    "tdarr-control": (["tdarr"], {"api_key": ["api key", "credential", "password"]}),
    "unifi": (["unifi"], {"username": ["username"], "password": ["password"], "api_key": ["api key"]}),
    "unraid-control": (["unraid"], {"api_key": ["api key", "credential"], "ssh_password": ["ssh password"]}),
    "synology-nas": (["synology", "diskstation", "dsm"], {"username": ["username"], "password": ["password"]}),
    "comfyui-control": (["civitai"], {"civitai_token": ["token", "credential", "password"]}),
    "opencode-control": (["opencode"], {"username": ["username"], "password": ["password"]}),
    # searxng-control needs no secrets (ssh_user is not sensitive; comes from example config)
}


def op(*args: str) -> str:
    res = subprocess.run(["op", *args, "--format", "json"], capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"op {' '.join(args)}: {res.stderr.strip()}")
    return res.stdout


def field_value(item: dict, hints: list[str]) -> str | None:
    fields = item.get("fields", [])
    for hint in hints:  # explicit label match wins, in hint order
        for f in fields:
            if hint in (f.get("label") or "").lower() and f.get("value"):
                return f["value"]
    # purpose fallback for username/password-shaped hints
    purpose = {"username": "USERNAME", "password": "PASSWORD"}
    for hint in hints:
        want = purpose.get(hint.split()[-1])
        for f in fields:
            if want and f.get("purpose") == want and f.get("value"):
                return f["value"]
    return None


def main() -> int:
    dry = "--dry-run" in sys.argv
    vault = sys.argv[sys.argv.index("--vault") + 1] if "--vault" in sys.argv else "Gregory"

    try:
        op("whoami")
    except Exception as e:
        print(f"No active 1Password session ({e}).\nRun:  eval $(op signin)  first.", file=sys.stderr)
        return 1

    items = json.loads(op("item", "list", "--vault", vault))
    print(f"{len(items)} items in vault {vault!r}\n")

    written, missing = [], []
    for plugin, (keywords, wants) in SERVICES.items():
        example = ROOT / plugin / "config.example.json"
        cfg = json.loads(example.read_text())
        cfg.pop("_comment", None)

        matches = [i for i in items if any(k in i["title"].lower() for k in keywords)]
        if not matches:
            missing.append((plugin, f"no vault item matching {keywords}"))
            continue

        filled, unfilled = {}, []
        for m in matches:
            item = json.loads(op("item", "get", m["id"], "--vault", vault))
            for key, hints in wants.items():
                if key not in filled:
                    v = field_value(item, hints)
                    if v is not None:
                        filled[key] = v
        unfilled = [k for k in wants if k not in filled]
        if not filled:
            missing.append((plugin, f"matched {[m['title'] for m in matches]} but no usable fields"))
            continue

        cfg.update(filled)
        target = ROOT / plugin / "config.local.json"
        note = f" (unfilled: {unfilled})" if unfilled else ""
        print(f"{plugin}: {list(filled)} from {matches[0]['title']!r}{note}")
        if not dry:
            target.write_text(json.dumps(cfg, indent=2) + "\n")
            os.chmod(target, 0o600)
            written.append(plugin)

    if missing:
        print("\nNo config written for:")
        for plugin, why in missing:
            print(f"  {plugin}: {why}")
    print(f"\n{'DRY RUN — nothing written' if dry else f'{len(written)} config.local.json files written'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
