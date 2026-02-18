# Azure Functions Backend Template

Production-ready Azure Functions backend template for bootstrapping Micro SaaS applications. Designed to be cloned by infrastructure automation and deployed immediately.

## Overview

This is a **template repository** used by the MicroSaaS Factory. When a new application is created, this template is cloned with all environment variables pre-configured. The first CI/CD run deploys a fully functional API.

## Architecture

- **Runtime**: Azure Functions (Python 3.13, Consumption Y1)
- **Authentication**: Microsoft Entra External ID OAuth2
- **Database**: Azure Cosmos DB with Managed Identity (passwordless)
- **Observability**: OpenTelemetry → Grafana Cloud (OTLP)
- **CI/CD**: GitHub Actions

## Project Structure

```text
backend-template/
├── function_app.py                 # Ultra-thin wrapper (Azure Functions v2 entrypoint)
├── src/
│   ├── functions/
│   │   ├── __init__.py             # Exports app for function_app.py
│   │   └── http_functions.py       # Azure Functions HTTP adapters
│   ├── services/
│   │   └── endpoint_service.py     # Business logic (framework-agnostic)
│   ├── auth/
│   │   └── auth_service.py         # OAuth2 token validation
│   ├── database/
│   │   └── cosmos_service.py       # Cosmos DB with Managed Identity
│   ├── monitoring/
│   │   ├── otel_config.py          # OpenTelemetry configuration
│   │   └── monitor.py              # Monitoring service
│   ├── container.py                # Dependency injection
│   └── utils/
│       ├── config.py               # Environment configuration
│       └── logger.py               # Structured logging
├── .github/workflows/
│   ├── ci-cd.yml                   # Main deployment pipeline
│   ├── dependency-updates.yml      # Automated security updates
│   ├── grafana-sync.yml            # Dashboard/alert sync
│   └── security.yml                # Security scanning
├── grafana/
│   ├── dashboards/                 # Grafana dashboards (JSON)
│   └── alerts/                     # Alert rules (JSON)
├── tests/                          # Test suite
├── requirements.txt                # Python dependencies
├── requirements-dev.txt            # Development dependencies
└── host.json                       # Azure Functions config
```

The ultra-thin wrapper pattern separates Azure Functions runtime requirements from business logic:

- `function_app.py` at root: Required by Azure Functions v2, only imports and re-exports
- `src/functions/`: Azure Functions HTTP adapters (thin layer)
- `src/services/`: Business logic (testable without Azure runtime)

## Environment Variables

### Runtime (Pre-configured by Infrastructure)

| Variable                        | Purpose               | Example                                    |
| ------------------------------- | --------------------- | ------------------------------------------ |
| `COSMOSDB_ENDPOINT`             | Cosmos DB endpoint    | `https://account.documents.azure.com:443/` |
| `COSMOSDB_DATABASE_NAME`        | Database name         | `app1-db`                                  |
| `COSMOSDB_USERS_CONTAINER`      | Users container       | `users`                                    |
| `COSMOSDB_AUDITLOGS_CONTAINER`  | Audit logs container  | `auditlogs`                                |
| `COSMOSDB_RATELIMITS_CONTAINER` | Rate limits container | `ratelimits`                               |
| `AZURE_CLIENT_ID`               | Entra app client ID   | `12345678-...`                             |
| `AZURE_TENANT_ID`               | Entra tenant ID       | `87654321-...`                             |
| `OTEL_EXPORTER_OTLP_ENDPOINT`   | Grafana OTLP endpoint | `https://otlp-gateway.grafana.net/otlp`    |
| `OTEL_EXPORTER_OTLP_HEADERS`    | Grafana auth headers  | `Authorization=Basic <base64>`             |
| `OTEL_SERVICE_NAME`             | Service identifier    | `backend-template`                         |

### CI/CD Only (GitHub Secrets)

| Secret              | Purpose                   |
| ------------------- | ------------------------- |
| `COSMOSDB_KEY`      | Schema migrations only    |
| `AZURE_CREDENTIALS` | Deployment authentication |

## API Endpoints

| Endpoint            | Method | Auth   | Description                        | Rate Limit       |
| ------------------- | ------ | ------ | ---------------------------------- | ---------------- |
| `/api/health`       | GET    | None   | Health check                       | None             |
| `/api/auth/login`   | POST   | Bearer | Validate token, ensure user exists | 10/min per IP    |
| `/api/user/profile` | GET    | Bearer | Get user profile                   | 100/min per user |

## Rate Limiting

Built-in rate limiting using Cosmos DB (no Redis required):

- **Anonymous requests**: 20 requests/minute per IP address
- **Authenticated users**: 100 requests/minute per user ID
- **Auth endpoints**: 10 requests/minute per IP (prevents brute force)
- **Response headers**: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`
- **HTTP 429**: Returns rate limit info and `Retry-After` header when exceeded

**Storage**: Uses the `ratelimits` container with automatic TTL cleanup (no manual maintenance).

**Customization**: Edit `src/middleware/rate_limiter.py` to adjust limits or add per-endpoint rules.

## Authentication Flow

1. User authenticates with Microsoft Entra External ID (OAuth2)
2. Frontend receives `access_token` from Microsoft
3. Frontend calls `/api/auth/login` with `Authorization: Bearer <token>`
4. Backend validates JWT signature using Microsoft's JWKS
5. Backend extracts user claims (sub, email, name)
6. Backend ensures user exists in Cosmos DB (creates if new)
7. Backend logs to audit container
8. Backend returns user profile

## Local Development

```bash
# Install pip-tools
pip install pip-tools

# Install dependencies
pip-sync requirements.txt requirements-dev.txt

# Copy settings template
cp local.settings.json.template local.settings.json

# Update local.settings.json with your values
# - COSMOSDB_ENDPOINT, COSMOSDB_DATABASE_NAME
# - AZURE_CLIENT_ID, AZURE_TENANT_ID

# Start Azure Functions
func start
```

## Dependency Management

This project uses **pip-tools** for reproducible dependency management.

```bash
# Update dependencies to latest compatible versions
pip-compile --upgrade requirements.in
pip-compile --upgrade requirements-dev.in
pip-sync requirements.txt requirements-dev.txt

# Add new dependency
echo "new-package~=1.0.0" >> requirements.in
pip-compile requirements.in
pip-sync requirements.txt requirements-dev.txt
```

See `scripts/README.md` for more details.

## Testing

```bash
# Run tests
pytest

# With coverage
pytest --cov=src --cov-report=html
```

## Deployment

### Automatic (Recommended)

Push to `main` branch - GitHub Actions handles everything:

1. Runs tests
2. Builds deployment package
3. Deploys to Azure Functions
4. Syncs Grafana dashboards

### Manual

```bash
func azure functionapp publish <function-app-name>
```

## Database Schema

### Users Container

- **Partition Key**: `/userId`
- **Fields**: `id`, `userId`, `email`, `name`, `displayName`, `roles`, `createdAt`, `lastLoginAt`, `isActive`

### Audit Logs Container

- **Partition Key**: `/date` (format: `YYYY-MM-DD`)
- **TTL**: 30 days (automatic deletion)
- **Fields**: `id`, `date`, `userId`, `action`, `timestamp`, `statusCode`, `method`, `resource`, `metadata`, `ipAddress`, `userAgent`, `traceId`, `ttl`
- **Note**: Partition key is date-based for efficient range queries and automatic cleanup. Cross-partition queries are used when retrieving user-specific logs.

### Rate Limits Container

- **Partition Key**: `/key`
- **TTL**: 3600 seconds (1 hour, automatic cleanup)
- **Fields**: `id`, `key`, `endpoint`, `count`, `windowStart`, `ttl`
- **Note**: Flexible partitioning allows user-level (`user-12345`) or endpoint-level (`user-endpoint`) rate limiting.

**Note**: Cosmos DB containers are pre-created by infrastructure. Application initializes on startup via `CosmosService.initialize()`.

## Monitoring

Implements SRE Golden Signals:

- **Latency**: HTTP request duration
- **Traffic**: Requests per second
- **Errors**: Error rate and count
- **Saturation**: Database operation latency

Telemetry is batched per-request and sent to Grafana at request end to minimize latency.

## Customization

1. Update `APP_NAME` in environment
2. Add business logic in `src/services/endpoint_service.py`
3. Add Azure Functions adapters in `src/functions/http_functions.py`
4. Add Grafana dashboards to `grafana/dashboards/`
5. Configure alerts in `grafana/alerts/`

## Security

- RS256 JWT signature verification
- Managed Identity for database access
- Audit logging for all actions
- Automated dependency updates
- CI/CD security scanning

## Troubleshooting

### "Invalid token signature"

- Verify `AZURE_CLIENT_ID` matches token audience
- Check `AZURE_TENANT_ID` matches token issuer

### "Failed to connect to Cosmos DB"

- Ensure Managed Identity has "Cosmos DB Built-in Data Contributor" role
- Verify `COSMOSDB_ENDPOINT` is correct

### "Grafana telemetry not appearing"

- Check `GRAFANA_CLOUD_URL` and `GRAFANA_CLOUD_API_KEY`
- Verify API key has write permissions

## License

MIT License - customize and deploy as needed.

## Make targets

This project provides a `Makefile` with common developer targets. The `Makefile` creates and uses a local `.venv` by default and is safe to run on developer machines.

Common targets:

- `make deps` — create `.venv` (if missing) and install development dependencies from `requirements-dev.txt`.
- `make checks` — run linting, type checking, formatting checks, and a quick security scan (invokes `make deps`).
- `make start-emulator` — start the Cosmos DB emulator using `./scripts/run-emulator.sh`.
- `make stop-emulator` — stop and remove the emulator container using `./scripts/stop-emulator.sh`.
- `make integration` — start emulator (if necessary), ensure deps are installed, run integration tests against the emulator.
- `make act` — run the `checks` job locally with `act` (requires `act` installed).

- `make init` — initialize the repository for development: creates `.venv`, installs dev dependencies, and installs `pre-commit` hooks.
- `make precommit-install` — (helper) installs the `pre-commit` git hooks using the project's virtualenv.

Examples:

```bash
# install dev deps into .venv
make deps

# run the full check pipeline
make checks

# start emulator, run integration tests, then stop emulator
make start-emulator
make integration
make stop-emulator

# initialize repository (creates .venv, installs deps, installs pre-commit hooks)
make init
```

Override `.venv` location:

```bash
VENV_DIR=.env make checks
```

VS Code users: tasks are available in `.vscode/tasks.json` — open `Terminal → Run Task...` and choose `Run: checks (full)` or `Run: integration (full)` for a one-click run.

## Formatting and Linting

This repository uses **Black** for formatting and **Ruff** for linting. Black is the canonical formatter which guarantees stable, consistent formatting. Ruff is a very fast linter that detects potential bugs and enforces style and import ordering.

Why this setup:

- **Black** ensures everyone has identical formatting output.
- **Ruff** provides linting (flake8-like rules, bug detectors, import ordering) without replacing Black's canonical formatting.

## Pre-commit Hooks

Pre-commit hooks run automatically on every commit to catch issues early. The configuration uses strict defaults so projects created from this template start with the best possible code quality.

Hooks included:

| Hook                                   | Purpose                                     |
| -------------------------------------- | ------------------------------------------- |
| `trailing-whitespace`                  | Remove trailing whitespace                  |
| `end-of-file-fixer`                    | Ensure files end with newline               |
| `check-yaml` / `check-json`            | Validate syntax                             |
| `check-merge-conflict`                 | Detect unresolved merge markers             |
| `check-added-large-files`              | Prevent committing files > 500 KB           |
| `check-shebang-scripts-are-executable` | Ensure scripts with shebangs are executable |
| `black`                                | Format Python code                          |
| `isort`                                | Sort imports (Black-compatible profile)     |
| `ruff`                                 | Fast Python linter                          |
| `mypy`                                 | Static type checking                        |
| `bandit`                               | Security scanning for `src/`                |
| `prettier`                             | Format YAML, JSON, Markdown                 |
| `detect-secrets`                       | Prevent committing secrets                  |

Install hooks after cloning:

```bash
make init
```

Run all hooks manually:

```bash
pre-commit run --all-files
```

Run the checks locally:

```bash
# prepare environment
make deps

# run formatting check, linting, type checks and security scan
make checks

# if Black suggests fixes, apply them
.venv/bin/black src/ tests/

# re-run checks
make checks
```
