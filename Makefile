.PHONY: check reconcile test test-js help

OPENCODE_DIR ?= $(HOME)/.config/opencode
PYTHON ?= python3
NODE ?= node

.DEFAULT_GOAL := check

check: test test-js  ## Validate fragments, reconcile logic, and guard plugin

reconcile:  ## Merge opencode/ fragments into ~/.config/opencode
	OPENCODE_DIR="$(OPENCODE_DIR)" $(PYTHON) scripts/reconcile.py

test:  ## Run unit tests
	$(PYTHON) -m unittest discover -s tests -v

test-js:  ## Run guard plugin tests
	$(NODE) --test tests/test_plugin.test.js

help:  ## Show available targets
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'
