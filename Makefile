PYTHON ?= python
PIP ?= $(PYTHON) -m pip

.PHONY: dev-setup lint format format-check type-check test coverage build clean docs-check docs-serve docs-build docs-deploy

dev-setup:
	$(PIP) install -e ".[dev,docs]" pip-audit

lint:
	ruff check .

format:
	ruff format .

format-check:
	ruff format . --check

type-check:
	mypy --strict executionkit/

test:
	pytest

coverage:
	pytest --cov=executionkit --cov-fail-under=80

build:
	$(PYTHON) -m build

clean:
	rm -rf build dist mkdocs-site .pytest_cache .mypy_cache .ruff_cache *.egg-info

docs-serve:
	mkdocs serve

docs-check:
	$(PYTHON) scripts/check_doc_facts.py
	$(PYTHON) -m mkdocs build --strict

docs-build:
	$(PYTHON) -m mkdocs build --strict

docs-deploy:
	mkdocs gh-deploy --force
