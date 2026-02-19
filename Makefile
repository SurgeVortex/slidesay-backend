.PHONY: setup test lint check

setup:
	python3 -m venv --without-pip .venv
	curl -sS https://bootstrap.pypa.io/get-pip.py | .venv/bin/python3
	.venv/bin/pip install -r requirements.txt -q
	.venv/bin/pip install -r requirements-dev.txt -q

test:
	AZURE_CLIENT_ID=test AZURE_TENANT_ID=test .venv/bin/python -m pytest tests/ -q

lint:
	.venv/bin/python -m ruff check src/ tests/

check: lint test
