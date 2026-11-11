#!/usr/bin/env python3
"""Merge repository OpenCode config into ~/.config/opencode.

Fragments in opencode/opencode.json.d/ are merged in filename order. The result
is deep-merged over the destination, so local-only keys survive. For lists the
fragment order is authoritative because OpenCode applies the last match;
destination-only items are kept first, where they cannot override a fragment.
Rules are matched by (action, resource), so editing a fragment replaces the
deployed rule instead of leaving the old one alongside it.
"""

import json
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def destination(override):
    """Default destination; an empty override is not a valid target."""
    return Path(override or Path.home() / ".config" / "opencode")


DEST = destination(os.environ.get("OPENCODE_DIR"))


def rule_identity(item):
    """Identity for a permission/policy rule; None for any other list value."""
    if isinstance(item, dict) and "action" in item and "resource" in item:
        return (item["action"], item["resource"])
    return None


def merge(dest, source):
    """Source wins. For lists, source order wins; dest-only items stay first."""
    if isinstance(dest, dict) and isinstance(source, dict):
        return {
            key: merge(dest.get(key), value)
            for key, value in {**dest, **source}.items()
        }
    if isinstance(dest, list) and isinstance(source, list):
        source_ids = {
            identity
            for identity in (rule_identity(item) for item in source)
            if identity is not None
        }
        if source_ids and all(rule_identity(item) is not None for item in source):
            kept = [
                item
                for item in dest
                if rule_identity(item) not in source_ids and item not in source
            ]
            return kept + source
        return [item for item in dest if item not in source] + source
    return source


def load_fragment(fragment):
    """Read a fragment, dropping full-line `//` comments.

    Comments are source-only. The merged `opencode.json` stays plain JSON.
    Full-line only so a URL inside a string is never treated as a comment.
    """
    text = fragment.read_text(encoding="utf-8")
    uncommented = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("//")
    )
    try:
        data = json.loads(uncommented)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{fragment}: invalid JSON after comment stripping: {exc}"
        ) from exc
    if not isinstance(data, dict):
        raise ValueError(
            f"{fragment}: expected a JSON object, got {type(data).__name__}"
        )
    return data


def desired_config(fragments_dir):
    """Merge every fragment in filename order; numeric prefixes set precedence."""
    if not fragments_dir.is_dir():
        raise FileNotFoundError(f"fragments directory not found: {fragments_dir}")
    data = {}
    for fragment in sorted(fragments_dir.glob("*.json")):
        data = merge(data, load_fragment(fragment))
    return data


def write(path, text, backup=True):
    """Install text at path, atomically, mode 0600. Returns True when changed."""
    target = path.resolve() if path.is_symlink() else path
    if target.exists() and target.read_text(encoding="utf-8") == text:
        if target.stat().st_mode & 0o777 != 0o600:
            target.chmod(0o600)
            return True
        return False
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if backup and target.exists():
        shutil.copy2(target, target.with_name(target.name + "~"))
    temp = target.with_name(target.name + ".tmp")
    try:
        temp.write_text(text, encoding="utf-8")
        temp.chmod(0o600)
        os.replace(temp, target)
    finally:
        if temp.exists():
            temp.unlink()
    return True


def reconcile_plugins(dest):
    """Install guard plugins. No `~` backups here: the plugins directory is
    auto-scanned, so a stale copy would be loaded. Stale files are not removed."""
    changed = []
    for plugin in sorted((ROOT / "opencode" / "plugins").glob("*.js")):
        if write(
            dest / "plugins" / plugin.name,
            plugin.read_text(encoding="utf-8"),
            backup=False,
        ):
            changed.append(f"plugins/{plugin.name}")
    return changed


def reconcile(dest):
    """Merge fragments over the live file, then install AGENTS.md and plugins.

    Returns the relative paths that changed.
    """
    path = dest / "opencode.json"
    if path.exists():
        try:
            live = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}: invalid JSON: {exc}") from exc
        if not isinstance(live, dict):
            raise ValueError(
                f"{path}: expected a JSON object, got {type(live).__name__}"
            )
    else:
        live = {}
    config = merge(live, desired_config(ROOT / "opencode" / "opencode.json.d"))
    changed = []
    if write(path, json.dumps(config, indent=2) + "\n"):
        changed.append("opencode.json")
    agents_md = (ROOT / "opencode" / "AGENTS.md").read_text(encoding="utf-8")
    if write(dest / "AGENTS.md", agents_md):
        changed.append("AGENTS.md")
    changed.extend(reconcile_plugins(dest))
    return changed


def main():
    changed = reconcile(DEST)
    if changed:
        print(f"OpenCode config updated in {DEST}: {', '.join(changed)}.")
    else:
        print(f"OpenCode config already in sync in {DEST}.")


if __name__ == "__main__":
    main()
