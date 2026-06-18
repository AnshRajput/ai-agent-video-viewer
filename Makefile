.PHONY: help sync check compile test all

help:
	@echo "Targets:"
	@echo "  sync     copy root SKILL.md + scripts/ into the plugin mirror"
	@echo "  check    fail if the plugin mirror has drifted from root"
	@echo "  compile  byte-compile all Python in both trees"
	@echo "  test     compile + mirror check + unit tests"
	@echo "  all      sync then test"

sync:
	python3 scripts/sync_mirror.py

check:
	python3 scripts/sync_mirror.py --check

compile:
	python3 -m py_compile scripts/*.py skills/ai-agent-video-viewer/scripts/*.py

test: compile check
	python3 -m unittest discover -s tests -v

all: sync test
