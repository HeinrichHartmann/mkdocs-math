UV ?= uv

install:
	$(UV) sync --all-extras

test:
	$(UV) run pytest mkdocs_math/tests/ -v -k "not Layer3"

test-all:
	$(UV) run pytest mkdocs_math/tests/ -v

lint:
	$(UV) run ruff check mkdocs_math/

clean:
	rm -rf .cache/ .pytest_cache/ mkdocs_math/tests/test_project/build/
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

.PHONY: install test test-all lint clean
