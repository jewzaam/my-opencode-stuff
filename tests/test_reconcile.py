#!/usr/bin/env python3
"""Checks for fragment loading and the order-sensitive permission result."""

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.reconcile import (  # noqa: E402
    desired_config,
    destination,
    merge,
    reconcile,
    write,
)

FRAGMENTS = ROOT / "opencode" / "opencode.json.d"

SENSITIVE_ACTIONS = ("read", "grep", "edit", "write", "glob")
SENSITIVE_PATHS = {
    "*.env",
    "*.env.*",
    "*.kdbx",
    "*/.aws/*",
    "*/.ssh/*",
    "*/.kube/*",
    "*/.ocm/*",
    "*/.claude/*credentials*",
    "*/.config/gws/*",
    "*/.config/gh/*",
    "*/.git-credentials",
    "*/.netrc",
    "*/.docker/*",
    "*/.npmrc",
}
ENV_EXAMPLE = "*.env.example"

PERMISSION_ACTIONS = {
    "*",
    "shell",
    "read",
    "edit",
    "write",
    "grep",
    "glob",
    "external_directory",
    "skill",
    "question",
}


def glob_to_regex(pattern):
    """Translate an OpenCode glob to a regex body.

    `@opencode/core@2.2.7` replaces every `*` with `.*` and `?` with one
    character; everything else is literal.
    """
    return "".join(
        ".*" if char == "*" else "." if char == "?" else re.escape(char)
        for char in pattern
    )


def matches(pattern, resource):
    """Whole-value OpenCode glob match.

    A pattern ending in `" *"` compiles to `"( .*)?"`, so it also matches the
    same value without the trailing space-and-star (`git status` for
    `git status *`).
    """
    if pattern.endswith(" *"):
        regex = glob_to_regex(pattern[:-2]) + "( .*)?"
    else:
        regex = glob_to_regex(pattern)
    return re.fullmatch(regex, resource) is not None


def resolve(rules, action, resource):
    """OpenCode semantics: last matching rule wins; None means no rule matched."""
    effect = None
    for rule in rules:
        if rule["action"] not in ("*", action):
            continue
        pattern = rule["resource"]
        if action in ("read", "edit", "external_directory"):
            pattern = os.path.expanduser(pattern)
        if matches(pattern, resource):
            effect = rule["effect"]
    return effect


def resolve_policy(policies, resource):
    """Policies are binary and last-match wins; no match leaves the action allowed."""
    effect = "allow"
    for statement in policies:
        if matches(statement["resource"], resource):
            effect = statement["effect"]
    return effect


class TestMerge(unittest.TestCase):
    def test_dest_only_keys_survive(self):
        self.assertEqual(merge({"theme": "x"}, {}), {"theme": "x"})

    def test_source_scalar_wins(self):
        self.assertEqual(merge({"theme": "x"}, {"theme": "y"}), {"theme": "y"})

    def test_lists_union_source_last(self):
        self.assertEqual(merge({"a": [1, 2]}, {"a": [2, 3]}), {"a": [1, 2, 3]})

    def test_source_order_wins_for_shared_rules(self):
        dest = {"a": [{"r": "b"}, {"r": "a"}]}
        source = {"a": [{"r": "a"}, {"r": "b"}]}
        self.assertEqual(merge(dest, source)["a"], source["a"])

    def test_dest_only_rules_stay_ahead_of_source(self):
        dest = {"a": [{"r": "local"}, {"r": "a"}]}
        source = {"a": [{"r": "a"}, {"r": "b"}]}
        self.assertEqual(
            merge(dest, source)["a"],
            [{"r": "local"}, {"r": "a"}, {"r": "b"}],
        )

    def test_edited_rule_replaces_the_deployed_one(self):
        dest = {
            "permissions": [
                {"action": "shell", "resource": "git status *", "effect": "allow"},
                {"action": "shell", "resource": "local *", "effect": "allow"},
            ]
        }
        source = {
            "permissions": [
                {"action": "shell", "resource": "git status *", "effect": "ask"}
            ]
        }
        self.assertEqual(
            merge(dest, source)["permissions"],
            [
                {"action": "shell", "resource": "local *", "effect": "allow"},
                {"action": "shell", "resource": "git status *", "effect": "ask"},
            ],
        )


class TestReconcile(unittest.TestCase):
    def test_live_file_is_merged_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            local = {
                "theme": "local-theme",
                "permissions": [
                    {"action": "shell", "resource": "my-tool *", "effect": "allow"}
                ],
                "policies": [
                    {"action": "tool.use", "resource": "provider:x", "effect": "deny"}
                ],
            }
            (dest / "opencode.json").write_text(json.dumps(local))
            reconcile(dest)
            got = json.loads((dest / "opencode.json").read_text())
            self.assertEqual(got["theme"], "local-theme")
            self.assertIn(local["permissions"][0], got["permissions"])
            self.assertIn(local["policies"][0], got["policies"])
            self.assertIn(
                {"action": "shell", "resource": "git status *", "effect": "allow"},
                got["permissions"],
            )

    def test_guard_plugin_is_installed_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            reconcile(dest)
            plugin = dest / "plugins" / "harness-guards.js"
            self.assertTrue(plugin.exists())
            self.assertIn("harness_guards.block_commands", plugin.read_text())
            self.assertEqual(plugin.stat().st_mode & 0o777, 0o600)

            before = plugin.read_text()
            reconcile(dest)
            self.assertEqual(plugin.read_text(), before)

    def test_changed_files_are_backed_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            old_config = {"theme": "old-theme"}
            old_agents = "old agents\n"
            (dest / "opencode.json").write_text(json.dumps(old_config))
            (dest / "AGENTS.md").write_text(old_agents)
            reconcile(dest)
            self.assertEqual(
                json.loads((dest / "opencode.json~").read_text()), old_config
            )
            self.assertEqual((dest / "AGENTS.md~").read_text(), old_agents)

    def test_install_modes_agents_md_and_second_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            reconcile(dest)
            installed = (
                dest / "opencode.json",
                dest / "AGENTS.md",
                dest / "plugins" / "harness-guards.js",
            )
            for path in installed:
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(
                (dest / "AGENTS.md").read_text(encoding="utf-8"),
                (ROOT / "opencode" / "AGENTS.md").read_text(encoding="utf-8"),
            )

            before = {path: path.read_bytes() for path in installed}
            self.assertFalse(reconcile(dest))
            for path, content in before.items():
                self.assertEqual(path.read_bytes(), content)
            for path in installed:
                self.assertFalse(path.with_name(path.name + "~").exists())

    def test_cli_writes_to_opencode_dir_and_reports_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {**os.environ, "OPENCODE_DIR": tmp}
            command = [sys.executable, str(ROOT / "scripts" / "reconcile.py")]
            first = subprocess.run(
                command, cwd=ROOT, env=env, capture_output=True, text=True
            )
            self.assertEqual(first.returncode, 0)
            self.assertIn("updated", first.stdout)
            self.assertIn(tmp, first.stdout)
            self.assertIn("opencode.json", first.stdout)
            for path in (
                Path(tmp) / "opencode.json",
                Path(tmp) / "AGENTS.md",
                Path(tmp) / "plugins" / "harness-guards.js",
            ):
                self.assertTrue(path.exists())

            second = subprocess.run(
                command, cwd=ROOT, env=env, capture_output=True, text=True
            )
            self.assertEqual(second.returncode, 0)
            self.assertIn("already in sync", second.stdout)

    def test_empty_opencode_dir_falls_back_to_default(self):
        self.assertEqual(
            destination(""), Path.home() / ".config" / "opencode"
        )

    def test_malformed_fragment_names_the_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            fragments = Path(tmp)
            bad = fragments / "99-bad.json"
            bad.write_text("{ not json }", encoding="utf-8")
            with self.assertRaises(ValueError) as caught:
                desired_config(fragments)
            self.assertIn("99-bad.json", str(caught.exception))

    def test_non_object_fragment_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fragments = Path(tmp)
            (fragments / "01-array.json").write_text("[]", encoding="utf-8")
            with self.assertRaises(ValueError) as caught:
                desired_config(fragments)
            self.assertIn("01-array.json", str(caught.exception))

    def test_missing_fragments_directory_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                desired_config(Path(tmp) / "absent")

    def test_malformed_live_file_names_the_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            (dest / "opencode.json").write_text("{ not json }", encoding="utf-8")
            with self.assertRaises(ValueError) as caught:
                reconcile(dest)
            self.assertIn("opencode.json", str(caught.exception))

    def test_non_object_live_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            (dest / "opencode.json").write_text("[]", encoding="utf-8")
            with self.assertRaises(ValueError) as caught:
                reconcile(dest)
            self.assertIn("opencode.json", str(caught.exception))

    def test_write_repairs_mode_of_unchanged_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "file.txt"
            target.write_text("same\n", encoding="utf-8")
            target.chmod(0o644)
            self.assertTrue(write(target, "same\n"))
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            self.assertFalse(write(target, "same\n"))

    def test_write_follows_a_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            real = Path(tmp) / "real.json"
            real.write_text("old\n", encoding="utf-8")
            link = Path(tmp) / "link.json"
            link.symlink_to(real)
            self.assertTrue(write(link, "new\n"))
            self.assertTrue(link.is_symlink())
            self.assertEqual(real.read_text(encoding="utf-8"), "new\n")

    def test_plugin_directory_gets_no_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            reconcile(dest)
            self.assertFalse(
                (dest / "plugins" / "harness-guards.js~").exists()
            )


class TestFragments(unittest.TestCase):
    def setUp(self):
        self.config = desired_config(FRAGMENTS)

    def test_every_rule_has_three_fields(self):
        for rule in self.config["permissions"]:
            self.assertEqual(set(rule), {"action", "resource", "effect"})
            self.assertIn(rule["action"], PERMISSION_ACTIONS)
            self.assertIsInstance(rule["resource"], str)
            self.assertTrue(rule["resource"])
            self.assertIn(rule["effect"], {"allow", "deny", "ask"})
        for policy in self.config["policies"]:
            self.assertEqual(set(policy), {"action", "resource", "effect"})
            self.assertEqual(policy["action"], "tool.use")
            self.assertIsInstance(policy["resource"], str)
            self.assertTrue(policy["resource"])
            self.assertIn(policy["effect"], {"allow", "deny"})

    def test_full_line_comments_are_stripped(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "a.json").write_text(
                '// note\n{"permissions": []}', encoding="utf-8"
            )
            self.assertEqual(desired_config(Path(tmp)), {"permissions": []})

    def test_shell(self):
        rules = self.config["permissions"]
        self.assertEqual(resolve(rules, "shell", "git status --short"), "allow")
        self.assertEqual(resolve(rules, "shell", "git status"), "allow")
        self.assertEqual(resolve(rules, "shell", "git push origin main"), "deny")
        # A trailing " *" also matches the bare command.
        self.assertEqual(resolve(rules, "shell", "git push"), "deny")
        self.assertEqual(resolve(rules, "shell", "git add"), "deny")
        self.assertEqual(resolve(rules, "shell", "rm -rf build"), "deny")
        self.assertEqual(resolve(rules, "shell", "cat ~/.ssh/id_rsa"), "ask")
        self.assertEqual(resolve(rules, "shell", "git commit"), "deny")
        self.assertEqual(resolve(rules, "shell", "git commit -m x"), "deny")
        self.assertEqual(resolve(rules, "shell", "git checkout main"), "deny")
        self.assertEqual(resolve(rules, "shell", "git stash list"), "deny")
        self.assertEqual(resolve(rules, "shell", "chmod 755 file"), "deny")
        self.assertEqual(resolve(rules, "shell", "dd if=x of=y"), "deny")
        self.assertEqual(resolve(rules, "shell", "semgrep scan ."), "deny")
        self.assertEqual(resolve(rules, "shell", "make check"), "allow")
        self.assertEqual(
            resolve(rules, "shell", "gws gmail users messages get abc"), "allow"
        )
        self.assertEqual(resolve(rules, "shell", "gws gmail users messages send"), "ask")
        # 05-global-allow: bare pwd and own skills paths only.
        self.assertEqual(resolve(rules, "shell", "pwd"), "allow")
        self.assertEqual(resolve(rules, "shell", "~/.claude/skills/x"), "allow")
        self.assertEqual(resolve(rules, "shell", "$HOME/.claude/skills/x"), "allow")
        self.assertEqual(
            resolve(rules, "shell", "/home/other/.claude/skills/x"), "ask"
        )
        # gh: api and token-printing forms fall through to ask.
        self.assertEqual(resolve(rules, "shell", "gh auth status"), "allow")
        self.assertEqual(
            resolve(rules, "shell", "gh auth status --show-token"), "deny"
        )
        self.assertEqual(resolve(rules, "shell", "gh auth status -t"), "deny")
        self.assertEqual(
            resolve(rules, "shell", "gh api --method=DELETE repos/o/r"), "ask"
        )
        # Interpreters that can read or execute files ask.
        self.assertEqual(resolve(rules, "shell", "awk 'BEGIN{system(\"id\")}'"), "ask")
        self.assertEqual(resolve(rules, "shell", "sed -n '1p' .env.local"), "ask")
        self.assertEqual(resolve(rules, "skill", "fix"), "allow")
        # `commit` falls through to ask: commits stay deliberate.
        self.assertEqual(resolve(rules, "skill", "commit"), "ask")

    def test_reads(self):
        rules = self.config["permissions"]
        self.assertEqual(resolve(rules, "read", "/repo/.env"), "deny")
        self.assertEqual(resolve(rules, "read", "/repo/.env.local"), "deny")
        self.assertEqual(resolve(rules, "read", "/repo/.env.example"), "allow")
        self.assertEqual(resolve(rules, "read", "/home/u/.ssh/id_rsa"), "deny")
        # glob `*` spans dots and slashes
        self.assertEqual(resolve(rules, "read", "/repo/secrete.env.stuff"), "deny")
        # matched by *.env, not by *.env.*
        self.assertEqual(resolve(rules, "read", "test.env"), "deny")
        # matched by *.env.*: the trailing * matches zero characters
        self.assertEqual(resolve(rules, "read", "test.env."), "deny")
        self.assertEqual(resolve(rules, "read", "foo.envrc"), "allow")
        self.assertEqual(resolve(rules, "read", "/repo/main.py"), "allow")

    def test_edits(self):
        rules = self.config["permissions"]
        self.assertEqual(resolve(rules, "edit", "repo/main.py"), "ask")
        self.assertEqual(resolve(rules, "edit", "/repo/main.py"), "ask")
        self.assertEqual(
            resolve(rules, "edit", str(Path.home() / "source/knowledgebase/x.md")),
            "allow",
        )
        self.assertEqual(
            resolve(rules, "edit", str(Path.home() / "source/standards/x.md")),
            "allow",
        )
        self.assertEqual(resolve(rules, "edit", "/repo/.env"), "deny")
        self.assertEqual(resolve(rules, "edit", "/repo/.env.local"), "deny")
        self.assertEqual(resolve(rules, "edit", "/repo/.env.example"), "allow")
        self.assertEqual(resolve(rules, "edit", "/home/u/.ssh/id_rsa"), "deny")
        self.assertEqual(resolve(rules, "edit", "/home/u/.kube/config"), "deny")
        self.assertEqual(resolve(rules, "edit", "/home/u/.ocm/config"), "deny")
        self.assertEqual(
            resolve(rules, "edit", "/home/u/.claude/credentials.json"), "deny"
        )

    def test_grep_and_credentials_denies(self):
        rules = self.config["permissions"]
        self.assertEqual(resolve(rules, "grep", "/repo/.env"), "deny")
        self.assertEqual(resolve(rules, "grep", "/repo/.env.example"), "allow")
        self.assertEqual(resolve(rules, "grep", "/home/u/.ssh/id_rsa"), "deny")
        self.assertEqual(
            resolve(rules, "grep", "/home/u/.claude/credentials.json"), "deny"
        )
        self.assertEqual(resolve(rules, "read", "/home/u/.kube/config"), "deny")
        self.assertEqual(resolve(rules, "read", "/home/u/.ocm/config"), "deny")
        self.assertEqual(
            resolve(rules, "read", "/home/u/.claude/credentials.json"), "deny"
        )

    def test_write_and_glob_denies(self):
        rules = self.config["permissions"]
        for action in ("write", "glob"):
            with self.subTest(action=action):
                self.assertEqual(resolve(rules, action, "/repo/.env"), "deny")
                self.assertEqual(resolve(rules, action, "/repo/.env.local"), "deny")
                self.assertEqual(
                    resolve(rules, action, "/repo/.env.example"), "allow"
                )
                self.assertEqual(
                    resolve(rules, action, "/home/u/.ssh/authorized_keys"), "deny"
                )
                self.assertEqual(
                    resolve(rules, action, "/home/u/.aws/credentials"), "deny"
                )
                self.assertEqual(
                    resolve(rules, action, "/home/u/.claude/credentials.json"),
                    "deny",
                )

    def test_sensitive_paths_are_complete_for_every_action(self):
        """The 50-secrets list is duplicated per action and mirrored as
        `tool.use <action>:<resource>` policies. Pin the set once; every copy
        must cover it exactly, so dropping a path anywhere fails."""
        self.assertEqual(len(SENSITIVE_PATHS), 14)
        expected = {path: "deny" for path in SENSITIVE_PATHS}
        expected[ENV_EXAMPLE] = "allow"
        permissions = self.config["permissions"]
        policies = self.config["policies"]
        for action in SENSITIVE_ACTIONS:
            with self.subTest(action=action):
                permission_map = {
                    rule["resource"]: rule["effect"]
                    for rule in permissions
                    if rule["action"] == action
                    and (rule["resource"] in SENSITIVE_PATHS or rule["resource"] == ENV_EXAMPLE)
                }
                self.assertEqual(permission_map, expected)
                policy_map = {}
                for policy in policies:
                    prefix, _, resource = policy["resource"].partition(":")
                    if prefix == action:
                        policy_map[resource] = policy["effect"]
                self.assertEqual(policy_map, expected)

    def test_matcher_semantics(self):
        cases = [
            # Documented examples from @opencode/core@2.2.7.
            ("git status *", "git status", "allow"),
            ("git status *", "git status --short", "allow"),
            ("git status *", "git statuses", None),
            ("a*b", "a/b", "allow"),
            ("a*b", "ab", "allow"),
            ("a?b", "a/b", "allow"),
            ("a?b", "ab", None),
            ("a**b", "a/b", "allow"),
        ]
        for pattern, resource, expected in cases:
            rules = [{"action": "shell", "resource": pattern, "effect": "allow"}]
            with self.subTest(pattern=pattern, resource=resource):
                self.assertEqual(resolve(rules, "shell", resource), expected)

    def test_new_fragments(self):
        rules = self.config["permissions"]
        # 06-skill-scripts: interpreter-pinned script allow, fixed mkdir.
        self.assertEqual(
            resolve(rules, "shell", "bash ~/.claude/skills/dump/scripts/x.py"),
            "allow",
        )
        self.assertEqual(
            resolve(
                rules, "shell", "curl ~/.claude/skills/dump/scripts/x.py"
            ),
            "ask",
        )
        self.assertEqual(
            resolve(rules, "shell", "mkdir -p /tmp/cited-research"), "allow"
        )
        self.assertEqual(
            resolve(rules, "shell", "rm -rf ~/.claude/skills/dump/scripts/x"),
            "deny",
        )
        # 60-gws-read: reads allowed, unlisted mutation falls through to ask.
        self.assertEqual(resolve(rules, "shell", "gws drive files get abc"), "allow")
        self.assertEqual(resolve(rules, "shell", "gws drive files delete abc"), "ask")
        # 80-openshell: reads allowed, mutation falls through to ask.
        self.assertEqual(resolve(rules, "shell", "openshell sandbox list"), "allow")
        self.assertEqual(resolve(rules, "shell", "openshell sandbox delete x"), "ask")

    def test_external_directories(self):
        rules = self.config["permissions"]
        home = Path.home()
        self.assertEqual(
            resolve(rules, "external_directory", str(home / "source/knowledgebase/x.md")),
            "allow",
        )
        self.assertEqual(
            resolve(rules, "external_directory", str(home / "source/standards/x.md")),
            "allow",
        )
        self.assertEqual(
            resolve(rules, "external_directory", str(home / ".claude/skills/x")),
            "allow",
        )
        self.assertEqual(
            resolve(
                rules,
                "external_directory",
                str(home / ".local/share/opencode/tool-output/x"),
            ),
            "allow",
        )
        self.assertEqual(
            resolve(rules, "external_directory", "/tmp/elsewhere/file"), "ask"
        )

    def test_denies_have_matching_policies(self):
        permission_denies = {
            (rule["action"], rule["resource"])
            for rule in self.config["permissions"]
            if rule["effect"] == "deny"
        }
        policy_denies = set()
        for policy in self.config["policies"]:
            if policy["action"] != "tool.use" or policy["effect"] != "deny":
                continue
            action, _, resource = policy["resource"].partition(":")
            policy_denies.add((action, resource))
        self.assertEqual(permission_denies, policy_denies)

    def test_policies_keep_env_example_readable(self):
        policies = self.config["policies"]
        self.assertEqual(resolve_policy(policies, "read:/repo/.env"), "deny")
        self.assertEqual(resolve_policy(policies, "read:/repo/.env.example"), "allow")
        self.assertEqual(resolve_policy(policies, "read:/repo/secrete.env.stuff"), "deny")
        self.assertEqual(resolve_policy(policies, "read:test.env"), "deny")
        self.assertEqual(resolve_policy(policies, "read:test.env."), "deny")
        self.assertEqual(resolve_policy(policies, "read:foo.envrc"), "allow")
        self.assertEqual(resolve_policy(policies, "edit:/repo/.env"), "deny")
        self.assertEqual(resolve_policy(policies, "edit:/repo/.env.example"), "allow")
        self.assertEqual(resolve_policy(policies, "read:/home/u/.kube/config"), "deny")
        self.assertEqual(resolve_policy(policies, "grep:/home/u/.ssh/id_rsa"), "deny")
        self.assertEqual(resolve_policy(policies, "shell:git commit"), "deny")
        self.assertEqual(resolve_policy(policies, "shell:git stash list"), "deny")
        self.assertEqual(resolve_policy(policies, "shell:semgrep scan ."), "deny")


if __name__ == "__main__":
    unittest.main()
