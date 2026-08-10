# San Diego Service Operations Intelligence
#
# Validate the published portfolio snapshot with `make test` and `make verify`.
# Those checks need no downloaded City data. `make all` is a refresh workflow:
# it downloads the City's rolling extracts, rebuilds the outputs with current
# data, and may produce figures that differ from the published snapshot.

PYTHON      ?= python3
VENV        := .venv
BIN         := $(VENV)/bin
PY          := $(BIN)/python
PIP         := $(BIN)/pip
STREAMLIT   := $(BIN)/streamlit

.DEFAULT_GOAL := help
.PHONY: help install download download-check audit analyze dashboard dashboard-app \
        screenshots excel test verify review clean clean-all all

help: ## Show this help
	@echo "San Diego Service Operations Intelligence"
	@echo
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[1m%-16s\033[0m %s\n", $$1, $$2}'
	@echo
	@echo "Published snapshot: make install && make test && make verify"
	@echo "Current-data refresh: make download && make all (figures may differ)"

# --- environment -------------------------------------------------------------
$(BIN)/python:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --quiet --upgrade pip

install: $(BIN)/python ## Create .venv and install pinned dependencies
	$(PIP) install --quiet -r requirements.txt
	@echo "Environment ready. Validate with: make test && make verify"

# --- data --------------------------------------------------------------------
download: ## Retrieve the official City extracts into data/raw/ (~245 MB)
	$(PY) scripts/download_data.py

download-check: ## HEAD each official URL without downloading
	$(PY) scripts/download_data.py --check-only

# --- analysis ----------------------------------------------------------------
analyze: ## Run the SQL layer -> data/aggregates/
	$(PY) -m src.pipeline

audit: ## Build base tables and run the data-quality checks
	$(PY) -m src.pipeline --base
	$(PY) -m src.audit

# --- outputs -----------------------------------------------------------------
excel: ## Build the Excel review workbook
	$(PY) -m src.build_excel

screenshots: ## Capture dashboard screenshots (needs Chrome; skipped if absent)
	-$(PY) scripts/capture_screenshots.py

dashboard: ## Build the static dashboard, Excel workbook and screenshots
	$(PY) -m src.build_dashboard
	$(MAKE) excel
	$(MAKE) screenshots

dashboard-app: ## Launch the interactive Streamlit dashboard
	$(STREAMLIT) run 05_dashboard/app.py

# --- quality gates -----------------------------------------------------------
test: ## Run the test suite (no downloaded data required)
	$(PY) -m pytest

verify: ## Re-check every written figure against the generated data
	$(PY) scripts/verify_claims.py

review: ## Regenerate REVIEW_PACKET.md
	$(PY) scripts/build_review_packet.py

# --- everything --------------------------------------------------------------
all: ## Refresh with current City data; rebuild outputs and checks
	$(MAKE) download
	$(PY) -m src.pipeline
	$(PY) -m src.audit
	$(MAKE) dashboard
	$(MAKE) test
	$(MAKE) verify
	$(MAKE) review
	@echo
	@echo "Done. Start with README.md, then 05_dashboard/dashboard.html"

# --- cleanup -----------------------------------------------------------------
clean: ## Remove generated outputs, keeping downloaded source data
	rm -rf data/processed/* data/aggregates/*
	@touch data/processed/.gitkeep data/aggregates/.gitkeep

clean-all: clean ## Also remove downloaded source data and the virtualenv
	rm -rf $(VENV)
	find data/raw -type f ! -name '.gitkeep' -delete
