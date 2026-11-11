# my-opencode-stuff

Versioned global configuration for OpenCode V2.

Permissions live in `opencode/opencode.json.d/*.json`, one file per concern. `make reconcile` merges them in filename order (the numeric prefix is precedence) and deep-merges the result over `~/.config/opencode/opencode.json`, so local-only keys survive. Fragment order is authoritative; local-only rules are kept ahead of the fragments so they cannot override one. It also installs `opencode/AGENTS.md` and the guard plugin. Files that change get a `~` backup, except plugin files: the plugins directory is auto-scanned, so a stale copy would load. `AGENTS.md` is fully owned by this repo. `service.json`, credentials, and other files are left alone. A rule edited in place (same `action` and `resource`) replaces the deployed rule. Removing a rule or plugin from the source does not remove it from an already-reconciled live file, because it is indistinguishable from a local rule; delete it there by hand.

Preview a reconcile with `make reconcile OPENCODE_DIR=/tmp/preview`. Run `make check` before reconciling. It loads every fragment, validates rule shape, asserts the order-sensitive outcomes (for example `git push` resolves to deny and `.env.example` to allow), and runs the guard-plugin tests. The guard-plugin tests use the real `harness_guards` when it is importable and otherwise fall back to a minimal stub in `tests/fixtures/harness_guards`, so a real guard check needs `harness_guards` importable (installed or on `PYTHONPATH`). `make check` needs `node` on PATH for the guard-plugin tests (`NODE=` overrides the binary); the Python tests use `python3` (`PYTHON=` overrides the interpreter).

## Ordering and matching

- Fragments merge in lexicographic filename order, so the numeric prefix is the only precedence mechanism. Order inside a file is kept as written.
- Permissions and policies both use **last matching rule wins**. Put broad rules first, exceptions and denies last. A new broad `ask` at the end would override every deny before it.
- Patterns are globs, not regex: `*` matches zero or more characters including `/` and `.`; `?` matches one. `read:*.env.*` matches `.env.local` and `secrete.env.stuff`. It does not match `test.env` (the separate `read:*.env` rule catches that), but it does match `test.env.` because the trailing `*` matches zero characters. `foo.envrc` matches neither.
- A policy `allow` does not grant access. It only lifts an earlier policy deny, after which permission rules decide.
- Fall-through: `00-baseline.json` leads with `{ "action": "*", "resource": "*", "effect": "ask" }`, which lands after OpenCode's prepended base `*:* allow` and overrides it. A permission check that no later rule matches therefore resolves to `ask`. A policy check with no match is allowed; policies only tighten.
- Resource paths: only a leading `~`, `~/`, `$HOME`, or `$HOME/` is expanded, at config load, for `read`, `edit`, and `external_directory`. `$PWD` and `./` stay literal and match nothing, and `{env:VAR}` resolves at load time rather than per project. In-project paths are matched location-relative; paths outside the location are canonical absolute.
- Do **not** add a blanket `edit * allow` to emulate `acceptEdits`. It also matches absolute paths, and the compensating `edit /* ask` only catches POSIX-absolute resources — not Windows drive/UNC paths. A saved "Allow always" for an external directory can add a durable `allow` that defeats the boundary. Edits fall through to ask; only explicitly named absolute paths are allowed.
- Fragments accept full-line `//` comments, stripped when merging. The deployed `opencode.json` stays plain JSON. Comments mark broad rules and where later fragments close them.

The config asks before edits, shell commands, and external-directory access, pre-approves the common read-only Git/GitHub/`gws`/make/check commands, and hard-denies the most important prohibited shell commands. `read`, `grep`, `edit`, `write`, and `glob` all deny the same sensitive-path list. This is **not** a shell sandbox: permission globs are best-effort, and shell commands can still read files or perform side effects.

## Hooks

`opencode/plugins/harness-guards.js` is deployed to `~/.config/opencode/plugins/`, the global V2 plugin directory reported by third-party plugin docs; confirm the first load after reconciling. It registers `tool.execute.before` and `permission.evaluate` and shells out to the two `harness_guards` Python modules owned by `my-claude-stuff`, so Claude Code, Codex, and OpenCode run one guard definition. The plugin closes gaps permission globs cannot express: flags before a subcommand (`git -C /repo push`), path tokens inside shell commands, WebFetch URLs (`file://` is rejected by the path guard), patch target paths, grep/glob tool paths, environment-dump segments after a chain operator, heredocs, process substitution, and `..` traversal in allowlisted skill paths. It spawns Python from a neutral directory so a project-local `harness_guards` package cannot shadow the installed guard.

Command chains are split on `&&`, `||`, `|&`, a lone `&`, `;`, `|`, and newlines (respecting quotes) and each segment is resolved against the deployed rules, matching Claude's per-command evaluation: two allowed commands chain fine, a denied segment blocks, and any other segment downgrades the whole call to `ask`. Substitution contents (`$(...)`, backticks) are checked the same way. Residual: nested substitution is evaluated as one segment, and shell redirection writes (`> file`) are not treated as edits. The Python guard still sees the unsplit command, so a segment the splitter mishandles is also checked by the deny patterns there.

Prerequisite: `harness_guards` must be importable by the `python3` OpenCode inherits. That normally already holds after `my-claude-stuff`'s `make reconcile` runs `python3 -m pip install --user .`. Override the interpreter with `OPENCODE_GUARD_PYTHON` (arguments allowed, e.g. `py -3`); a `PYTHONPATH` pointing at the `my-claude-stuff` checkout also works.

If a guard cannot run, the plugin rejects the action with `BLOCKED: <exact error>. Refusing to run unguarded; fix harness_guards or set OPENCODE_GUARD_PYTHON.` The model sees the rejection and must choose a path that does not depend on the broken guard. It also logs the error once via `console.error`. If the deployed `opencode.json` cannot be read, the plugin registers deny-all hooks and refuses every action with the same fail-closed message instead of falling back to empty rules. Renaming the plugin leaves the old file auto-loading until it is deleted by hand.

These guards are for host use. Inside an OpenShell sandbox the sandbox policy is the security boundary; do not treat this plugin as containment there.

Not ported: explicit MCP tool allow rules, WebFetch domain allowlists, Claude plugin/statusline settings, and skill `!` command injection (OpenCode does not expand it). Any permission action the plugin does not model is downgraded to `ask`, so an MCP call reaching the permission hook is prompted rather than silently allowed; a call that bypasses that hook is not seen.

## Installation

`harness_guards` must be importable by the `python3` OpenCode inherits; `make reconcile` in `my-claude-stuff` installs it. Then deploy this config:

```bash
make reconcile
```

Preview with `make reconcile OPENCODE_DIR=/tmp/preview` before writing `~/.config/opencode`. `make reconcile` is user-only; do not run it in an agent session.

## Usage

- `make check` — run the Python and guard-plugin tests.
- `make reconcile` — merge the fragments into the live config and install `AGENTS.md` and the guard plugin.
- `make help` — list targets.

## Development

Fragments live in `opencode/opencode.json.d/`; numeric prefixes set precedence. `opencode/AGENTS.md` holds the global user rules and `opencode/plugins/harness-guards.js` is the hook layer. Run `make check` before reconciling.

- OpenCode V2 config reference: https://opencode.ai/v2/docs/config
- Permission behavior: https://opencode.ai/v2/docs/permissions
- Policy behavior: https://opencode.ai/v2/docs/policies
