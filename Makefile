.PHONY: install dev test lint fmt typecheck run clean

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
