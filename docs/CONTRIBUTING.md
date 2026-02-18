# Contributing Guide

Welcome to the backend template! This guide covers everything you need to get started.

## Quick Start

```bash
# Clone the repository
git clone <repo-url>
cd backend-template

# Set up development environment
make init

# Run all checks (formatting, linting, type checking)
make checks

# Run unit tests
make test
```

That's it! You're ready to develop.

## Development Workflow

### 1. Create a Branch

```bash
git checkout -b feature/your-feature-name
```

### 2. Make Changes

Follow the guides for common tasks:

- [Adding an endpoint](HOW_TO_ADD_ENDPOINT.md)
- [Adding a service](HOW_TO_ADD_SERVICE.md)

### 3. Verify Locally

```bash
# Run all checks
make checks

# Run tests
make test

# Start local function app (optional)
make dev
```

### 4. Commit

```bash
# Pre-commit hooks run automatically
git add .
git commit -m "feat: add item listing endpoint"
```

### 5. Push and Create PR

```bash
git push origin feature/your-feature-name
```

CI will run automatically on your PR.

## Project Structure

```text
.
├── function_app.py          # Azure Functions entrypoint (DON'T ADD LOGIC HERE)
├── src/
│   ├── functions/           # HTTP adapters (thin layer)
│   │   └── http_functions.py
│   ├── services/            # Business logic (framework-agnostic)
│   │   └── endpoint_service.py
│   ├── interfaces/          # Contracts/interfaces
│   ├── auth/                # Authentication service
│   ├── database/            # Cosmos DB service
│   ├── middleware/          # Rate limiter, etc.
│   ├── monitoring/          # OpenTelemetry, logging
│   ├── container.py         # Dependency injection
│   └── utils/               # Config, logger
├── tests/
│   ├── conftest.py          # Pytest fixtures
│   ├── test_doubles.py      # Fakes and mocks
│   └── test_*.py            # Test files
├── grafana/                 # Dashboards and alerts
└── docs/                    # Documentation
```

## Code Standards

### Python Style

- **Formatting**: Black (line length 100)
- **Linting**: Ruff
- **Type Hints**: Required on all functions
- **Docstrings**: Required on public functions

```python
async def create_item(
    self,
    request: HttpRequest,
    monitor: IMonitoringService
) -> HttpResponse:
    """
    Create a new item for the authenticated user.

    Args:
        request: HTTP request with item data in body
        monitor: Monitoring service for logging

    Returns:
        HttpResponse with created item or error
    """
    # Implementation
```

### Architecture Rules

1. **Separation of Concerns**: HTTP handling in `functions/`, business logic in `services/`
2. **Dependency Injection**: Use `container.py` for service instantiation
3. **Interfaces First**: Define interface before implementation
4. **Tenant Isolation**: Every database query must filter by user ID

### Testing Requirements

- All new code must have tests
- Test files named `test_<module>.py`
- Use pytest with async support
- Use fakes from `test_doubles.py` (not mocks when possible)

## Available Make Commands

| Command                     | Description                                         |
| --------------------------- | --------------------------------------------------- |
| `make init`                 | Set up virtual environment and install dependencies |
| `make deps`                 | Install dependencies only                           |
| `make checks`               | Run Black, Ruff, mypy, and Bandit                   |
| `make test`                 | Run unit tests                                      |
| `make dev`                  | Start local Azure Functions server                  |
| `make integration`          | Run integration tests with Cosmos emulator          |
| `make openapi`              | Generate OpenAPI specification                      |
| `make precommit-install`    | Install pre-commit hooks                            |
| `make precommit-autoupdate` | Update pre-commit hooks                             |

## Common Issues

### "Module not found" Errors

Make sure you're using the virtual environment:

```bash
source .venv/bin/activate
```

### Type Checking Errors

For TYPE_CHECKING imports:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.interfaces import IAuthService

def my_func() -> "IAuthService":  # Quote the type
    pass
```

### Pre-commit Failing

Run the checks manually to see detailed errors:

```bash
make checks
```

### Tests Failing

Check that fakes are configured correctly:

```python
@pytest.fixture
def mock_auth_service():
    fake = FakeAuthService()
    fake.set_token_payload({"oid": "user-123"})  # Configure expected behavior
    return fake
```

## Environment Variables

For local development, create `local.settings.json`:

```bash
cp local.settings.json.template local.settings.json
```

Edit with your local values. **Never commit this file.**

## Commit Message Format

Use [Conventional Commits](https://www.conventionalcommits.org/):

- `feat: add item creation endpoint`
- `fix: handle null email in auth`
- `test: add rate limiter tests`
- `docs: update contributing guide`
- `refactor: extract validation logic`
- `chore: update dependencies`

## Getting Help

- Check [AI_INSTRUCTIONS.md](AI_INSTRUCTIONS.md) for quick patterns
- Read the specific how-to guides for detailed walkthroughs
- Look at existing code for examples
