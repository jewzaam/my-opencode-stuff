# my-opencode-stuff

Versioned global configuration for OpenCode V2.

Permissions live in `opencode/opencode.json.d/*.json`, one file per concern. `make reconcile` merges them in filename order (the numeric prefix is precedence) and deep-merges the result over `~/.config/opencode/opencode.json`, so local-only keys survive. Fragment order is authoritative; local-only rules are kept ahead of the fragments so they cannot override one. It also installs `opencode/AGENTS.md`. Files that change get a `~` backup. `AGENTS.md` is fully owned by this repo. `service.json`, credentials, and other files are left alone. Removing a rule from a fragment does not remove it from an already-reconciled live file, because local rules are preserved. Delete it there once.

Preview a reconcile with `make reconcile OPENCODE_DIR=/tmp/preview`. Run `make check` before reconciling. It loads every fragment, validates rule shape, and asserts the order-sensitive outcomes (for example `git push` resolves to deny and `.env.example` to allow).

## Ordering and matching

- Fragments merge in lexicographic filename order, so the numeric prefix is the only precedence mechanism. Order inside a file is kept as written.
- Permissions and policies both use **last matching rule wins**. Put broad rules first, exceptions and denies last. A new broad `ask` at the end would override every deny before it.
- Patterns are globs, not regex: `*` matches zero or more characters including `/` and `.`; `?` matches one. `read:*.env.*` matches `.env.local` and `secrete.env.stuff`. It does not match `test.env` (the separate `read:*.env` rule catches that), but it does match `test.env.` because the trailing `*` matches zero characters. `foo.envrc` matches neither.
- A policy `allow` does not grant access. It only lifts an earlier policy deny, after which permission rules decide.
- Fall-through: a permission check with no matching rule is `ask`, but OpenCode prepends a base `*:* allow`, so actions not mentioned here are effectively allowed. A policy check with no match is allowed; policies only tighten.

The config asks before shell commands and external-directory access, pre-approves a small subset of read-only Git/GitHub and check commands, and hard-denies the most important prohibited shell commands and sensitive direct reads. This is **not** a shell sandbox: command matching and directory inference are best-effort, and shell commands can still read files or perform side effects. Claude-only hooks, plugins, statusline, MCP credentials, and the large GWS allowlist were not copied. Those need separate OpenCode-specific decisions.

- OpenCode V2 config reference: https://opencode.ai/v2/docs/config
- Permission behavior: https://opencode.ai/v2/docs/permissions
- Policy behavior: https://opencode.ai/v2/docs/policies
