.PHONY: build run test lint format tidy clean

build:
	python -m build

run:
	shufflebase serve

test:
	pytest

lint:
	ruff check src tests
	mypy src/shufflebase

format tidy:
	ruff check --fix src tests
	ruff format src tests

clean:
	rm -rf build dist *.egg-info .pytest_cache .ruff_cache .mypy_cache .coverage htmlcov
	find . -name "__pycache__" -type d -prune -exec rm -rf {} +
