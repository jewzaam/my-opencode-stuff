# my-opencode-stuff

Global OpenCode configuration. `opencode/opencode.json.d/` is the source of truth for permissions and policies. `opencode/AGENTS.md` is the global user rules installed to `~/.config/opencode/AGENTS.md`. `opencode/plugins/harness-guards.js` is the OpenCode hook layer.

## Commands

- `make check` — run the Python and guard-plugin tests
- `make reconcile` — **USER ONLY**. Writes `~/.config/opencode/`. Never run it against the default destination; the preview form below is safe
- Preview a reconcile with `make reconcile OPENCODE_DIR=/tmp/preview`

## Architecture

- Fragments merge in lexicographic filename order. Numeric prefixes set precedence.
- Permissions and policies use last-match-wins. Keep broad rules first, exceptions and denies last.
- Reconcile merges over the live `opencode.json`. Rules are matched by `(action, resource)`, so an edited fragment rule replaces the deployed one; a rule removed from the fragments is still kept, because it is indistinguishable from a local rule. Delete removed rules from the live file by hand.
- `opencode/plugins/harness-guards.js` is copied to `~/.config/opencode/plugins/`. It spawns `python3 -m harness_guards.block_commands` and `block_paths` from `my-claude-stuff` via a neutral working directory with the implicit cwd path disabled (so a project-local package cannot shadow it); it does not contain the guard patterns. It splits command chains and resolves each segment against the deployed rules (Claude-style): allowed segments chain, denied ones block, anything else downgrades to ask. It also rejects environment-dump segments, heredocs, process substitution, and `..` traversal in allowlisted skill paths.
- The plugin fails closed when Python or the module is unavailable: `execute.before` rejects, `permission.evaluate` denies, and the model sees the exact error. `OPENCODE_GUARD_PYTHON` selects the interpreter.
- `tests/test_reconcile.py` pins ordering-sensitive permission outcomes; `tests/test_plugin.test.js` pins payload translation and hook behavior.
