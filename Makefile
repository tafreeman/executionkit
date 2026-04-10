PYTHON ?= python
PIP ?= $(PYTHON) -m pip

.PHONY: dev-setup lint format format-check type-check test coverage build clean docs-serve docs-build docs-deploy

dev-setup:
	$(PIP) install -e ".[dev]"

lint:
	ruff check .

format:
	ruff format .

format-check:
	ruff format . --check

type-check:
	mypy --strict executionkit/

test:
	pytest -m "not integration"

coverage:
	pytest --cov=executionkit --cov-fail-under=80

build:
	$(PYTHON) -m build

clean:
	rm -rf build dist mkdocs-site .pytest_cache .mypy_cache .ruff_cache *.egg-info

docs-serve:
	mkdocs serve

docs-build:
	mkdocs build

docs-deploy:
	mkdocs gh-deploy --force
