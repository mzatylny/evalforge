.PHONY: install test lint security run demo check

install:
	python -m pip install -e ".[dev]"

test:
	pytest --cov=evalforge --cov-report=term-missing

lint:
	ruff check .
	ruff format --check .

security:
	bandit -c pyproject.toml -r src

run:
	evalforge serve

demo:
	evalforge demo

check: lint test security
