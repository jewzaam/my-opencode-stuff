# my-opencode-stuff

Global OpenCode configuration. `opencode/opencode.json.d/` is the source of truth for permissions and policies. `opencode/AGENTS.md` is the global user rules installed to `~/.config/opencode/AGENTS.md`.

## Commands

- `make check` — run the fragment and reconcile tests
- `make reconcile` — **USER ONLY**. Writes `~/.config/opencode/`. Never run it
- Preview a reconcile with `make reconcile OPENCODE_DIR=/tmp/preview`

## Architecture

- Fragments merge in lexicographic filename order. Numeric prefixes set precedence.
- Permissions and policies use last-match-wins. Keep broad rules first, exceptions and denies last.
- Reconcile merges over the live `opencode.json`, preserving keys and rules it does not own. Removing a rule from a fragment does not remove it from an already-reconciled live file.
- `tests/test_reconcile.py` pins the ordering-sensitive outcomes.
