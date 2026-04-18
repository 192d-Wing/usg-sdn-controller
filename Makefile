.PHONY: install dev test lint fmt typecheck run clean \
        lab-render lab-up lab-verify lab-down integration

install:
	pip install -e '.[dev]'

dev: install

test:
	pytest -q

lint:
	ruff check src tests

fmt:
	ruff format src tests
	ruff check --fix src tests

typecheck:
	mypy src

run:
	uvicorn usg_sdn.api.app:app --reload --host :: --port 8080

clean:
	rm -rf build dist .pytest_cache .ruff_cache .mypy_cache *.egg-info
	find . -name __pycache__ -type d -exec rm -rf {} +

# --- containerlab integration ---------------------------------------------
# Requires containerlab + Docker + the cEOS image (set CEOS_IMAGE, default ceos:latest).
# See containerlab/README.md.

CLAB_TOPO ?= containerlab/campus-ceos.clab.yml
CLAB      ?= containerlab

lab-render:
	python containerlab/scripts/render_lab_configs.py

lab-up: lab-render
	cd $(CLAB) && containerlab deploy -t $(notdir $(CLAB_TOPO))

lab-verify:
	python containerlab/scripts/verify_evpn.py

lab-down:
	cd $(CLAB) && containerlab destroy -t $(notdir $(CLAB_TOPO)) --cleanup || true

# End-to-end integration: render → deploy → wait → verify → teardown.
# Intended target for CI (self-hosted, clab-capable runner) and local dev.
integration: lab-up
	@echo "waiting 90s for IS-IS + BGP-EVPN convergence..."
	@sleep 90
	$(MAKE) lab-verify || ( $(MAKE) lab-down ; exit 1 )
	$(MAKE) lab-down
