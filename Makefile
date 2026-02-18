# Makefile for common developer tasks (uses a local .venv by default)
.PHONY: help init deps checks test dev integration openapi clean
.PHONY: start-emulator stop-emulator act precommit-install precommit-autoupdate

# Virtual environment directory (override if you prefer a different path)
VENV_DIR?=.venv
PY := $(VENV_DIR)/bin/python
PIP := $(PY) -m pip
FUNC := func

# Default target - show help
.DEFAULT_GOAL := help

help: ## Show this help message
	@echo "Backend Template - Development Commands"
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@echo "Setup & Dependencies:"
	@grep -E '^(init|deps|precommit-install|precommit-autoupdate):.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  %-22s %s\n", $$1, $$2}'
	@echo ""
	@echo "Development:"
	@grep -E '^(dev|checks|test|openapi):.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  %-22s %s\n", $$1, $$2}'
	@echo ""
	@echo "Testing:"
	@grep -E '^(integration|start-emulator|stop-emulator|act):.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  %-22s %s\n", $$1, $$2}'
	@echo ""
	@echo "Maintenance:"
	@grep -E '^(clean):.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  %-22s %s\n", $$1, $$2}'

ensure-venv:
	@if [ ! -d "$(VENV_DIR)" ]; then \
		python3 -m venv "$(VENV_DIR)"; \
		echo "Created virtualenv at $(VENV_DIR)"; \
	fi

deps: ensure-venv ## Install all dependencies
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements-dev.txt

init: deps precommit-install ## Initialize repository for development (first time setup)
	@echo ""
	@echo "✅ Repository initialized!"
	@echo ""
	@echo "Next steps:"
	@echo "  1. Copy local.settings.json.template to local.settings.json"
	@echo "  2. Fill in your local configuration values"
	@echo "  3. Run 'make checks' to verify your setup"
	@echo "  4. Run 'make test' to run unit tests"
	@echo "  5. Run 'make dev' to start the local function app"
	@echo ""

precommit-install: deps ## Install pre-commit hooks
	@echo "Installing pre-commit into git hooks..."
	$(VENV_DIR)/bin/pre-commit install || (echo "pre-commit install failed"; exit 1)

precommit-autoupdate: deps ## Update pre-commit hooks to latest versions
	@echo "Updating pre-commit hooks to latest versions..."
	$(VENV_DIR)/bin/pre-commit autoupdate || (echo "pre-commit autoupdate failed"; exit 1)

checks: deps ## Run all linting, formatting, and type checks
	@echo "Running Black (formatting check)..."
	$(VENV_DIR)/bin/black --check src/ tests/ scripts/ --line-length=100
	@echo ""
	@echo "Running Ruff (linting)..."
	$(VENV_DIR)/bin/ruff check src/ tests/ scripts/ --output-format=github
	@echo ""
	@echo "Running mypy (type checking)..."
	$(VENV_DIR)/bin/mypy src/ --ignore-missing-imports --strict-optional
	@echo ""
	@echo "Running Bandit (security scanning)..."
	$(VENV_DIR)/bin/bandit -r src/ -ll || true
	@echo ""
	@echo "✅ All checks passed!"

test: deps ## Run unit tests
	@echo "Running unit tests..."
	$(VENV_DIR)/bin/pytest tests/ -v --tb=short -m "not integration"
	@echo ""
	@echo "✅ All tests passed!"

dev: deps ## Start local Azure Functions server
	@echo "Starting local Azure Functions server..."
	@echo "Make sure you have Azure Functions Core Tools installed: brew install azure-functions-core-tools@4"
	@echo ""
	@if [ ! -f "local.settings.json" ]; then \
		echo "⚠️  local.settings.json not found!"; \
		echo "   Copy local.settings.json.template to local.settings.json and fill in your values."; \
		exit 1; \
	fi
	$(FUNC) start --python

openapi: deps ## Generate OpenAPI specification
	@echo "Generating OpenAPI specification..."
	$(PY) scripts/generate_openapi.py
	@echo ""
	@echo "✅ OpenAPI spec generated at openapi/openapi.json"

start-emulator: ## Start Cosmos DB emulator (for integration tests)
	./scripts/run-emulator.sh

stop-emulator: ## Stop Cosmos DB emulator
	./scripts/stop-emulator.sh

integration: start-emulator deps ## Run integration tests (requires Cosmos emulator)
	@echo "Running integration tests..."
	@echo "Ensure COSMOSDB_KEY and JWT_SECRET_KEY are set in your environment."
	@echo ""
	export COSMOSDB_ENDPOINT=https://localhost:8081 && \
	export COSMOSDB_KEY=$${COSMOSDB_KEY:-} && \
	export COSMOSDB_DATABASE_NAME=testdb && \
	export COSMOSDB_USERS_CONTAINER=users && \
	export COSMOSDB_AUDITLOGS_CONTAINER=auditlogs && \
	export COSMOSDB_RATELIMITS_CONTAINER=ratelimits && \
	export ENVIRONMENT=testing && \
	export JWT_SECRET_KEY=$${JWT_SECRET_KEY:-} && \
	$(VENV_DIR)/bin/pytest tests/ -v --maxfail=1 -m "integration"

act: ## Run CI checks locally using act (requires act installed)
	act -j checks -P ubuntu-latest=nektos/act-environments-ubuntu:20.04

clean: ## Clean up generated files and caches
	@echo "Cleaning up..."
	rm -rf .pytest_cache
	rm -rf .mypy_cache
	rm -rf .ruff_cache
	rm -rf htmlcov
	rm -rf .coverage
	rm -rf src/__pycache__ tests/__pycache__
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "✅ Cleanup complete!"
