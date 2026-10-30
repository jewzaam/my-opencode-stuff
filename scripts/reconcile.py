#!/usr/bin/env python3
"""Merge repository OpenCode config into ~/.config/opencode.

Fragments in opencode/opencode.json.d/ are merged in filename order. The result
is deep-merged over the destination, so local-only keys survive. For lists the
fragment order is authoritative because OpenCode applies the last match;
destination-only items are kept first, where they cannot override a fragment.
"""

import json
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = Path(os.environ.get("OPENCODE_DIR", Path.home() / ".config" / "opencode"))


def merge(dest, source):
    """Source wins. For lists, source order wins; dest-only items stay first."""
    if isinstance(dest, dict) and isinstance(source, dict):
        return {
            key: merge(dest.get(key), value)
            for key, value in {**dest, **source}.items()
        }
    if isinstance(dest, list) and isinstance(source, list):
        return [item for item in dest if item not in source] + source
    return source


def desired_config(fragments_dir):
    """Merge every fragment in filename order; numeric prefixes set precedence."""
    data = {}
    for fragment in sorted(fragments_dir.glob("*.json")):
        data = merge(data, json.loads(fragment.read_text(encoding="utf-8")))
    return data


def write(path, text, mode):
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.exists():
        shutil.copy2(path, path.with_name(path.name + "~"))
    path.write_text(text, encoding="utf-8")
    path.chmod(mode)
    return True


def reconcile(dest):
    """Merge fragments over the live file, then install AGENTS.md."""
    path = dest / "opencode.json"
    live = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    config = merge(live, desired_config(ROOT / "opencode" / "opencode.json.d"))
    changed = write(path, json.dumps(config, indent=2) + "\n", 0o600)
    agents_md = (ROOT / "opencode" / "AGENTS.md").read_text(encoding="utf-8")
    return write(dest / "AGENTS.md", agents_md, 0o600) or changed


def main():
    changed = reconcile(DEST)
    print("OpenCode config updated." if changed else "OpenCode config already in sync.")


if __name__ == "__main__":
    main()
