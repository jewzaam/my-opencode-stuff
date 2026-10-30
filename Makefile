.PHONY: check reconcile test help

OPENCODE_DIR ?= $(HOME)/.config/opencode
PYTHON ?= python3

.DEFAULT_GOAL := check

check: test  ## Validate fragments and reconcile logic

reconcile:  ## Merge opencode/ fragments into $(OPENCODE_DIR)
	OPENCODE_DIR="$(OPENCODE_DIR)" $(PYTHON) scripts/reconcile.py

test:  ## Run unit tests
	$(PYTHON) -m unittest discover -s tests -v

help:  ## Show available targets
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'
