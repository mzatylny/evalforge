.PHONY: install test lint typecheck security run demo check

install:
	python -m pip install -e ".[dev]"

test:
	pytest --cov=evalforge --cov-report=term-missing

lint:
	ruff check .
	ruff format --check .

typecheck:
	mypy src/evalforge

security:
	bandit -c pyproject.toml -r src

run:
	evalforge serve

demo:
	evalforge demo

check: lint typecheck test security
