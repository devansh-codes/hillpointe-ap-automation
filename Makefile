# Reproduce everything. MODE: auto (Claude + cache, default) | offline (cache only) | labels (hand-labelled test fixtures)
MODE ?= auto
LABELS = --labels tests/fixtures/labels --labels tests/fixtures/labels/refs
FLAGS = $(if $(filter offline,$(MODE)),--offline,)$(if $(filter labels,$(MODE)),$(LABELS),)
AP = uv run ap

.PHONY: install test doctor evidence demo synthetic eval clean-outputs

install:            ## one-time setup
	uv sync

test:               ## full test suite (no API key needed)
	uv run pytest -q

doctor:             ## pre-flight checks
	$(AP) doctor

evidence:           ## deliverable 3: reset ledger → Batch 01 → rerun Batch 01 → Batch 02, then save snapshot 'submitted'
	$(AP) reset-state --yes
	$(AP) run 01_Invoice_Batch_01 $(FLAGS)
	$(AP) run 01_Invoice_Batch_01 $(FLAGS)
	$(AP) run 07_Invoice_Batch_02_Rerun $(FLAGS)
	$(AP) snapshot save submitted

ui:                 ## open the web app for the AP team (http://127.0.0.1:8765)
	$(AP) ui

demo: install doctor evidence   ## fresh clone → all evidence

synthetic:          ## regenerate the synthetic hold-out documents
	uv run python tests/synthetic/generate.py

eval:               ## score the model's extraction against the hand labels (needs API key or cache)
	$(AP) eval-extraction 01_Invoice_Batch_01 07_Invoice_Batch_02_Rerun 03_Purchase_Orders_and_Subcontracts \
	  --labels tests/fixtures/labels --labels tests/fixtures/labels/refs
