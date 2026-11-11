# Test fixtures

`harness_guards/` is a minimal stub of the deployed `harness_guards` package
from `my-claude-stuff`. It exists so the guard-plugin tests still run when the
real package is not importable.

It is not a second guard definition. It models only the deny patterns the
tests pin, so a green `make check` against the stub proves payload translation,
not full guard coverage. When `harness_guards` is importable, the suite uses
the real modules instead.
