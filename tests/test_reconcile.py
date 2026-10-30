#!/usr/bin/env python3
"""Checks for fragment loading and the order-sensitive permission result."""

import fnmatch
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.reconcile import desired_config, merge, reconcile  # noqa: E402

FRAGMENTS = ROOT / "opencode" / "opencode.json.d"


def resolve(rules, action, resource):
    """OpenCode semantics: last matching rule wins; None means no rule matched."""
    effect = None
    for rule in rules:
        if rule["action"] not in ("*", action):
            continue
        pattern = rule["resource"]
        if fnmatch.fnmatchcase(resource, pattern):
            effect = rule["effect"]
        elif pattern.endswith(" *") and resource == pattern[:-2]:
            effect = rule["effect"]
    return effect


def resolve_policy(policies, resource):
    """Policies are binary and last-match wins; no match leaves the action allowed."""
    effect = "allow"
    for statement in policies:
        if fnmatch.fnmatchcase(resource, statement["resource"]):
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


class TestFragments(unittest.TestCase):
    def setUp(self):
        self.config = desired_config(FRAGMENTS)

    def test_every_rule_has_three_fields(self):
        for rule in self.config["permissions"]:
            self.assertEqual(set(rule), {"action", "resource", "effect"})
            self.assertIn(rule["effect"], {"allow", "deny", "ask"})

    def test_loading_is_idempotent(self):
        self.assertEqual(desired_config(FRAGMENTS), self.config)

    def test_shell(self):
        rules = self.config["permissions"]
        self.assertEqual(resolve(rules, "shell", "git status --short"), "allow")
        self.assertEqual(resolve(rules, "shell", "git status"), "allow")
        self.assertEqual(resolve(rules, "shell", "git push origin main"), "deny")
        self.assertEqual(resolve(rules, "shell", "rm -rf build"), "deny")
        self.assertEqual(resolve(rules, "shell", "cat ~/.ssh/id_rsa"), "ask")

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
        self.assertEqual(resolve(rules, "edit", "/repo/.env"), "deny")
        self.assertEqual(resolve(rules, "edit", "/repo/.env.local"), "deny")
        self.assertEqual(resolve(rules, "edit", "/repo/.env.example"), "allow")
        self.assertEqual(resolve(rules, "edit", "/home/u/.ssh/id_rsa"), "deny")
        self.assertEqual(resolve(rules, "edit", "/repo/main.py"), "ask")

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


if __name__ == "__main__":
    unittest.main()
