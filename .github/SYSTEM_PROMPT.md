# Backend Application System Prompt

## Application Identity
- **App Name**: slidesay
- **App Display Name**: SlideSay.com – Presentation automation platform
- **Environment**: prod
- **Function App Name**: func-microsaas-factory-slidesay-prod
- **Resource Group**: rg-microsaas-factory-slidesay-app-prod
- **API Domain**: api-slidesay.isonet.casa

## Quick Reference Documentation

For common development tasks, read the relevant guide:

| Task | Documentation File |
|------|-------------------|
| **Quick patterns & rules** | `docs/AI_INSTRUCTIONS.md` |
| **Add a new endpoint** | `docs/HOW_TO_ADD_ENDPOINT.md` |
| **Add a new service** | `docs/HOW_TO_ADD_SERVICE.md` |
| **Testing patterns** | `docs/HOW_TO_TEST.md` |
| **Development workflow** | `docs/CONTRIBUTING.md` |
| **OpenAPI generation** | `openapi/README.md` |
| **Make commands** | Run `make help` |

**IMPORTANT**: Before adding endpoints or services, read the relevant HOW_TO guide.

## Technology Stack
- **Runtime**: Python 3.13
- **Framework**: Azure Functions (Python V2 programming model)
- **Hosting**: Azure Functions Flex Consumption (Linux)
- **Database**: Azure Cosmos DB for NoSQL (serverless)
- **Authentication**: Microsoft Entra ID (Azure AD) with JWT validation
- **Observability**: OpenTelemetry → Grafana Cloud (traces, metrics, logs)
- **Configuration**: Azure Function app settings

## Architecture Overview

You are building a serverless backend API for a multi-tenant SaaS application. The backend runs on Azure Functions and provides RESTful HTTP endpoints for the React frontend. All endpoints require authentication via Microsoft Entra ID bearer tokens. Data is stored in Azure Cosmos DB using passwordless authentication (managed identity).

### Key Architectural Principles
1. **Zero Trust Security**: Validate every request, trust no input
2. **Multi-Tenant Isolation**: Strictly enforce data isolation by authenticated user ID
3. **Stateless API**: No session state on server; use JWT claims for user context
4. **Idempotency**: GET, PUT, DELETE must be idempotent; use request IDs for POST
5. **Rate Limiting**: Enforce per-user rate limits using Cosmos DB
6. **Observability First**: Structured logging, distributed tracing, metrics for every request
7. **Fail Securely**: Default deny; graceful degradation; clear audit trails
8. **Framework Agnostic**: Separate business logic from hosting framework. Business logic should work with any HTTP framework (Azure Functions, FastAPI, Flask) without rewrites.

## Authentication & Authorization

### Microsoft Entra ID Token Validation
- **Tenant ID**: `4c0a147f-72de-4be4-a172-ec74c9f1cc1d`
- **Client ID (Audience)**: Configured in environment as `AZURE_CLIENT_ID`
- **Token Format**: JWT Bearer token in `Authorization` header
- **Validation Library**: `azure-identity` or `PyJWT` with Microsoft keys

### Authentication Requirements
1. **Every HTTP endpoint must validate bearer token** (except health checks)
2. Extract token from `Authorization: Bearer <token>` header
3. Validate token signature using Microsoft public keys (JWKS endpoint)
4. Verify token claims:
   - `aud` (audience): Must match your `AZURE_CLIENT_ID`
   - `iss` (issuer): Must be Microsoft Entra ID
   - `exp` (expiration): Token must not be expired
   - `nbf` (not before): Token must be valid now
   - `oid` or `sub` (user ID): Extract for tenant isolation
5. Return `401 Unauthorized` for invalid/missing tokens
6. Extract user ID from token claims (`oid` or `sub` claim) for data scoping

### API Scope & Audience
- **API Scope (configured in environment)**: `api://microsaas-factory-slidesay-prod/user_impersonation`
- When validating tokens for API access, accept tokens whose `aud` claim matches either the API Application ID URI portion (for example the value before `/user_impersonation`) or the backend app's client id (GUID). Configure `AZURE_API_SCOPE` in environment so clients request the correct scope.

### App Registration Notes (optional properties)
- Entra App Registrations support additional metadata you can set: homepage URL, logo, terms of service, privacy statement, and reply/redirect URIs.
- You can also enable external identity providers (social sign-in) in Entra (e.g., GitHub, Google, Facebook) under the Entra External Identities features or via identity providers. When enabled, Entra will federate the signin but the application flow in your code remains the same: your app still uses Entra-issued tokens and requests the same `AZURE_API_SCOPE`. No code changes are needed specifically to consume tokens from users who authenticated via a social provider — it's handled by Entra.

### Ensure App Is Configured For User Impersonation
- To allow user impersonation flow, make sure the API application registration has an `oauth2_permission_scope` defined (value `user_impersonation` or equivalent) and `identifier_uris` contains the Application ID URI used in `AZURE_API_SCOPE`.
- The frontend must request `AZURE_API_SCOPE` when acquiring tokens so Azure issues access tokens that include the API scope.

### Authorization Pattern
- **Tenant Isolation**: All database queries must filter by authenticated user ID
- **Role-Based Access**: Use token `roles` claim if role-based authorization needed
- **Audit Logging**: Use `MonitoringService.create_audit_log()` method that writes to Cosmos DB auditlogs container with automatic trace correlation
- **Principle of Least Privilege**: Users can only access their own data
- **First-Time Users**: The `get_or_create_user()` method returns a tuple `(User, is_new_user: bool)`. Login endpoints should return `isNewUser` field in response to enable frontend onboarding flows for first-time users.

### CORS Configuration
CORS is configured in infrastructure to allow:
- Frontend domain: `slidesay.isonet.casa`
- SWA default hostname: `*.azurestaticapps.net`
- Credentials: `true` (allows cookies/authorization headers)

## Database Architecture

### Azure Cosmos DB for NoSQL
- **Connection**: Managed Identity (passwordless) via `ChainedTokenCredential`
- **Endpoint**: Configured as `COSMOSDB_ENDPOINT` environment variable
- **Database Name**: Configured as `COSMOSDB_DATABASE_NAME` environment variable
- **SDK**: `azure-cosmos` Python package

### Authentication to Cosmos DB
Use `ChainedTokenCredential` for Cosmos DB authentication:
1. `ManagedIdentityCredential` (production - fast, direct)
2. `AzureCliCredential` (local development fallback)

This pattern provides fast cold starts by targeting Managed Identity first.

### Cosmos DB Containers

#### 1. Users Container
- **Name**: Configured as `COSMOSDB_USERS_CONTAINER` environment variable
- **Partition Key**: `/userId`
- **Purpose**: User profiles, preferences, application-specific user data
- **Access Pattern**: Point reads/writes by user ID
- **Example Document**:
```json
{
  "id": "user-12345",
  "userId": "00000000-0000-0000-0000-000000000000",
  "email": "user@example.com",
  "displayName": "John Doe",
  "preferences": {...},
  "createdAt": "2025-11-04T10:00:00Z",
  "updatedAt": "2025-11-04T10:00:00Z"
}
```

#### 2. Audit Logs Container
- **Name**: Configured as `COSMOSDB_AUDITLOGS_CONTAINER` environment variable
- **Partition Key**: `/date` (format: `YYYY-MM-DD`)
- **TTL**: 30 days (automatic deletion)
- **Purpose**: Audit trail of all user actions
- **Access Pattern**: Write-heavy; query by date range
- **Example Document**:
```json
{
  "id": "log-67890",
  "date": "2025-11-04",
  "userId": "00000000-0000-0000-0000-000000000000",
  "action": "update_profile",
  "resource": "/api/users/12345",
  "method": "PUT",
  "statusCode": 200,
  "timestamp": "2025-11-04T10:30:00Z",
  "ipAddress": "203.0.113.42",
  "userAgent": "Mozilla/5.0...",
  "ttl": 2592000
}
```

#### 3. Rate Limits Container
- **Name**: Configured as `COSMOSDB_RATELIMITS_CONTAINER` environment variable
- **Partition Key**: `/key` (flexible: user ID, IP, endpoint)
- **TTL**: 3600 seconds (1 hour, automatic cleanup)
- **Purpose**: Distributed rate limiting state
- **Access Pattern**: High-frequency reads/writes
- **Indexing**: Minimal (only `id` and partition key)
- **Example Document**:
```json
{
  "id": "ratelimit-user-12345-endpoint-/api/users",
  "key": "user-12345",
  "endpoint": "/api/users",
  "count": 42,
  "windowStart": "2025-11-04T10:00:00Z",
  "ttl": 3600
}
```

### Rate Limiting Strategy
1. **Per-User Rate Limits**: Recommend 100 requests/minute per user
2. **Per-Endpoint Limits**: More restrictive for expensive operations
3. **Implementation**:
   - Use `/key` partition with user ID for user-level limits
   - Use `/key` partition with `user-endpoint` for endpoint-level limits
   - Check count in current time window
   - Increment atomically (use Cosmos DB optimistic concurrency)
   - Return `429 Too Many Requests` with `Retry-After` header
4. **TTL Management**: Set `ttl` field to 3600 for automatic cleanup

## API Design

### HTTP Endpoints Structure
- **Base Path**: `/api`
- **Versioning**: Optional (e.g., `/api/v1/users`)
- **RESTful Conventions**:
  - `GET /api/resource` - List resources (paginated)
  - `GET /api/resource/{id}` - Get single resource
  - `POST /api/resource` - Create new resource
  - `PUT /api/resource/{id}` - Replace resource (full update)
  - `PATCH /api/resource/{id}` - Partial update
  - `DELETE /api/resource/{id}` - Delete resource

### Request Validation
1. **Schema Validation**: Use Python dataclasses with MyPy strict type checking for request body validation
2. **Input Sanitization**: Sanitize all user input
3. **Type Checking**: Validate parameter types (str, int, UUID, etc.)
4. **Business Logic Validation**: Enforce business rules
5. **Authorization Check**: Verify user can perform action on resource

### Response Format
**Success (200-299)** - Return direct objects:
```json
{
  "user": {
    "id": "user-12345",
    "email": "user@example.com",
    "displayName": "John Doe"
  }
}
```

Add `X-Trace-Id` response header with OpenTelemetry trace ID for correlation.

**Error (400-599)**:
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid input",
    "details": ["Field 'email' is required"]
  }
}
```

Add `X-Trace-Id` response header for debugging.

### HTTP Status Codes
- `200 OK`: Successful GET, PUT, PATCH
- `201 Created`: Successful POST
- `204 No Content`: Successful DELETE
- `400 Bad Request`: Validation error, malformed request
- `401 Unauthorized`: Missing or invalid authentication token
- `403 Forbidden`: Valid token but insufficient permissions
- `404 Not Found`: Resource doesn't exist
- `409 Conflict`: Resource conflict (e.g., duplicate ID)
- `429 Too Many Requests`: Rate limit exceeded
- `500 Internal Server Error`: Unhandled server error
- `503 Service Unavailable`: Temporary unavailability (e.g., database down)

### Pagination
Implement pagination based on your application requirements:
- Use Cosmos DB continuation tokens for sequential pagination (efficient, low cost)
- For parallel pagination, implement `totalCount` calculation via `COUNT(1)` query and page-based logic
- Return pagination metadata in response format that suits your API design

### Filtering & Sorting
- Query parameters: `?status=active&sortBy=createdAt&sortOrder=desc`
- Support common filters relevant to your data model
- Document supported filters in API

## Error Handling

### Exception Handling Pattern
1. **Try-Catch Blocks**: Wrap all business logic
2. **Specific Exceptions**: Catch specific exception types first
3. **Logging**: Log errors with context (user ID, request ID, stack trace)
4. **User-Friendly Messages**: Return sanitized error messages
5. **Audit Trail**: Log security-relevant errors to audit log

### Error Categories
- **Validation Errors** (400): Return field-specific errors
- **Authentication Errors** (401): "Invalid or expired token"
- **Authorization Errors** (403): "You don't have permission"
- **Not Found Errors** (404): "Resource not found"
- **Rate Limit Errors** (429): Include `Retry-After` header
- **Server Errors** (500): Log details, return generic message

### Logging Best Practices
- **Structured Logging**: Use JSON format
- **Log Levels**: DEBUG, INFO, WARNING, ERROR, CRITICAL
- **Context**: Include request ID, user ID, correlation ID
- **Sensitive Data**: Exclude passwords, tokens, and PII from logs
- **Performance**: Log request duration
- **Distributed Tracing**: Include trace/span IDs

## Observability & Monitoring

### Grafana Cloud Integration
- **Management Token**: Available as `GRAFANA_CLOUD_MANAGEMENT_TOKEN` in CI/CD only
- **Folder UID**: `slidesay-prod` (target for dashboards/alerts created by CI/CD)

### OpenTelemetry Observability

**Send all telemetry directly to Grafana Cloud using OpenTelemetry and OTLP exporters.**

#### Dependencies
Add OpenTelemetry packages to `requirements.in`:
```
opentelemetry-api
opentelemetry-sdk
opentelemetry-instrumentation-httpx
opentelemetry-exporter-otlp-proto-http
structlog
```

Use `opentelemetry-instrumentation-httpx` for HTTP client instrumentation if using httpx library.

#### Configuration
Configure OTLP exporters to send traces, metrics, and logs to Grafana Cloud in batch mode.

**Environment variables** (configured automatically):
- `OTEL_EXPORTER_OTLP_ENDPOINT`: Grafana Cloud OTLP endpoint URL
- `OTEL_EXPORTER_OTLP_HEADERS`: `Authorization=Bearer <token>` format
- `OTEL_SERVICE_NAME`: `slidesay-backend`
- `OTEL_RESOURCE_ATTRIBUTES`: `environment=prod,app=slidesay`

**Note on configuration sources**:
- Public/config variables (repo variables, not secrets):
  - `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`
  - `AZURE_CLIENT_ID` (audience)
  - `COSMOSDB_ENDPOINT`, `COSMOSDB_DATABASE_NAME`, `COSMOSDB_*_CONTAINER` names
  - `OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES`, `OTEL_EXPORTER_OTLP_ENDPOINT`
- CI/CD-only secrets (GitHub Actions secrets):
  - `GRAFANA_CLOUD_MANAGEMENT_TOKEN` (dashboard/alert management)
  - `OTEL_EXPORTER_OTLP_HEADERS` (Authorization=Bearer <token>)

*Removed `APPLICATIONINSIGHTS_CONNECTION_STRING` from CI secrets — Application Insights is configured directly on the Function App app settings.*

**Setup** (`src/monitoring/otel_config.py`):
1. Configure batch span processor for traces (export every 5s or 512 spans)
2. Configure batch metric reader for metrics (export every 60s)
3. Configure batch log processor for logs (export every 5s or 512 logs)
4. Set up auto-instrumentation for HTTP requests

OpenTelemetry handles all batching and exporting automatically in the background.

#### Distributed Tracing
OpenTelemetry auto-instrumentation creates spans for:
- HTTP requests to Azure Functions
- Cosmos DB operations
- Outbound HTTP calls
- Azure SDK operations

Add custom spans for business logic using `@tracer.start_as_current_span("operation_name")`.

#### Structured Logging
Use `structlog` for structured logging with OpenTelemetry trace context:

**Pattern**:
1. Configure structlog with JSON formatting
2. Use OpenTelemetry's `LoggerProvider` with OTLP exporter
3. Logs automatically include `trace_id` and `span_id` for correlation
4. Log at function entry/exit with request details

**Log levels**: INFO (operations), WARNING (recoverable issues), ERROR (failures), CRITICAL (system failures)

**Exclude from logs**: passwords, tokens, PII, full JWT tokens

#### Metrics
Use OpenTelemetry metrics API for:
- Request count/duration/status per endpoint
- Business metrics (signups, operations, feature usage)
- Database query timing
- Error rates and types
- Rate limit rejections

Metrics export automatically to Grafana Cloud Prometheus via OTLP batch exporter.

### Grafana Dashboards & Alerts

**Default Dashboards**:
Infrastructure deploys SRE golden signals dashboards to folder `slidesay-prod`:
- Request rates, error rates, latencies (p50/p95/p99)
- Database performance (Cosmos DB RU consumption)
- Function resource usage
- Rate limiting metrics

**Custom Dashboards** (optional):
Place dashboard JSON files in `grafana/dashboards/`. GitHub Actions automatically syncs changes to Grafana Cloud folder `slidesay-prod`.

**Custom Alerts** (optional):
Place alert JSON files in `grafana/alerts/`. GitHub Actions automatically configures them in Grafana Cloud.

## Security Best Practices

### Configuration Management
1. **Secrets management**: Store secrets in GitHub Secrets
2. **Environment variables**: Use environment variables via Function App settings for all configuration
3. **Managed Identity**: Use for Azure service authentication (Cosmos DB)
4. **GitHub Secrets**: CI/CD injects secrets as app settings during deployment

### Input Validation
1. **Whitelist approach**: Define allowed inputs explicitly
2. **Type validation**: Enforce data types
3. **Range validation**: Check min/max values
4. **Format validation**: Validate emails, UUIDs, dates
5. **Injection prevention**: Parameterized queries (Cosmos DB SDK handles this)
6. **File upload validation**: Check file types, sizes, scan for malware

### Output Encoding
1. **JSON responses**: Use built-in JSON serialization
2. **Error messages**: Sanitize error details
3. **Logs**: Exclude sensitive data (tokens, passwords, PII)

### Cosmos DB Security
1. **Managed Identity**: Use ChainedTokenCredential (ManagedIdentityCredential → AzureCliCredential)
2. **Partition key filtering**: Filter by partition key in all queries for performance and cost
3. **Tenant isolation**: Filter by user ID in all queries
4. **Parameterized queries**: Use SDK query methods
5. **Least privilege**: Function app has only necessary RBAC roles

### HTTPS & TLS
- Azure Functions enforces HTTPS
- Use TLS verification for all external API calls
- Use TLS 1.2 or higher

## Build & Deployment

### Project Structure

**Use dependency injection architecture for all services.**

Actual structure:
```
.
├── .funcignore
├── .github/workflows/             # CI/CD pipelines (pre-configured)
├── .gitignore
├── .pre-commit-config.yaml
├── .secrets.baseline
├── function_app.py                # Ultra-thin wrapper (Azure Functions entrypoint)
├── grafana/
│   ├── alerts/                    # Custom alerts (auto-synced to Grafana)
│   └── dashboards/                # Custom dashboards (auto-synced to Grafana)
├── docs/
│   ├── AI_INSTRUCTIONS.md         # Quick reference for AI agents (READ THIS)
│   ├── CONTRIBUTING.md            # Development workflow guide
│   ├── HOW_TO_ADD_ENDPOINT.md     # Step-by-step endpoint creation
│   ├── HOW_TO_ADD_SERVICE.md      # Step-by-step service creation
│   └── HOW_TO_TEST.md             # Testing patterns and fixtures
├── host.json
├── local.settings.json.template
├── Makefile                       # Development commands (make help)
├── openapi/
│   ├── openapi.json               # Auto-generated OpenAPI spec
│   └── README.md                  # OpenAPI usage guide
├── pyproject.toml
├── README.md
├── requirements-dev.in
├── requirements-dev.txt
├── requirements.in
├── requirements.txt
├── scripts/
│   ├── check_azure_settings.py
│   ├── generate_openapi.py        # OpenAPI generator
│   ├── sync_grafana.py
│   └── validate_grafana_config.py
├── src/
│   ├── __init__.py
│   ├── container.py               # DI container
│   ├── auth/
│   │   ├── __init__.py
│   │   └── auth_service.py
│   ├── database/
│   │   ├── __init__.py
│   │   └── cosmos_service.py
│   ├── functions/
│   │   ├── __init__.py
│   │   └── http_functions.py      # Azure Functions HTTP adapters (lazy loading)
│   ├── interfaces/
│   │   ├── __init__.py
│   │   ├── auth_interface.py
│   │   ├── database_interface.py
│   │   ├── endpoint_interface.py
│   │   ├── monitoring_interface.py
│   │   └── rate_limiter_interface.py
│   ├── middleware/
│   │   ├── __init__.py
│   │   └── rate_limiter.py
│   ├── monitoring/
│   │   ├── __init__.py
│   │   ├── otel_config.py         # OpenTelemetry configuration
│   │   └── monitor.py             # Monitoring service (logging, metrics, audit)
│   ├── services/
│   │   ├── __init__.py
│   │   └── endpoint_service.py    # Framework-agnostic business logic
│   └── utils/
│       ├── __init__.py
│       ├── config.py
│       └── logger.py              # Structlog with OpenTelemetry context
└── tests/
    ├── conftest.py
    ├── test_auth.py
    ├── test_database.py
    ├── test_doubles.py            # Test doubles (fakes, in-memory implementations)
    ├── test_endpoint_service.py
    └── test_monitoring.py
```

**Architecture**:
- **Ultra-Thin Wrapper**: `function_app.py` imports from `src/functions/http_functions.py`
- **Lazy Loading**: Container and services initialized at first request, not module load time
- **Dependency Injection**: Inject services via `container.py`
- **Interface-Driven**: Services implement interfaces for testability
- **OpenTelemetry**: Auto-instrumentation + structlog for logging
- **Rate Limiting**: Middleware applied to endpoints
- **Grafana Sync**: GitHub Actions auto-syncs `grafana/` to folder `slidesay-prod`

### Environment Variables
All required environment variables are automatically injected by GitHub Actions during deployment:
- Azure deployment credentials (function app, resource group, service principal)
- Cosmos DB connection details (endpoint, database, containers)
- OpenTelemetry configuration:
  - `OTEL_EXPORTER_OTLP_ENDPOINT`: Grafana Cloud OTLP endpoint
  - `OTEL_EXPORTER_OTLP_HEADERS`: Authorization header with embedded Grafana token
  - `OTEL_SERVICE_NAME`: Service name
  - `OTEL_RESOURCE_ATTRIBUTES`: Resource attributes
- Grafana Cloud settings:
  - `GRAFANA_CLOUD_MANAGEMENT_TOKEN`: Dashboard/alert management (CI/CD only)
  - `GRAFANA_CLOUD_FOLDER_UID`: `slidesay-prod`

Access via `os.environ` or `src/utils/config.py`.

### Deployment
CI/CD pipeline (`.github/workflows/ci-cd.yml`):
1. Lint, type-check, test
2. Build function app package
3. Deploy to Azure Functions
4. Run smoke tests
5. Monitor deployment in Grafana

## Development Guidelines

### Code Quality
- **Type Hints**: Use Python type hints everywhere
- **Docstrings**: Document functions and classes
- **Linting**: Use ruff (fast linter) and black (formatter)
- **Type Checking**: Use mypy with strict settings
- **Testing**: Unit tests (pytest), integration tests, E2E tests
- **Code Coverage**: Aim for >80% coverage
- **Security Scanning**: Scan dependencies for vulnerabilities (pip-audit, bandit)

### Python Best Practices
- **Python 3.13**: Use latest syntax and features
- **Async/await**: Use async for I/O operations (Cosmos DB, HTTP)
- **Context managers**: Use `with` statements
- **Exception handling**: Catch specific exceptions
- **Logging & Metrics**: Use `src/monitoring/monitor.py` (implements logger interface)
- **Configuration**: Environment variables via `src/utils/config.py`
- **Dependency injection**: Inject services from `container.py`
- **Separation of concerns**: Separate business logic from hosting framework (Azure Functions). Business logic should be framework-agnostic and receive data independent of HTTP framework.

### Azure Functions V2 Programming Model
- **Entry Point**: `function_app.py` at repo root imports `app` from `src/functions`
- **Decorators**: Use `@app.route()` decorator for HTTP triggers
- **Lazy Loading**: Container and services initialized on first request, not at module load time
- **Blueprint Pattern**: Organize functions in `src/functions/` directory
- **Async support**: Use async functions for I/O operations

### Flex Consumption Deployment
- **Bundled Dependencies**: Dependencies installed to `.python_packages/lib/site-packages/`
- **No Remote Build**: Set `scm-do-build-during-deployment: false` and `enable-oryx-build: false`
- **Runtime Configuration**: `FUNCTIONS_WORKER_RUNTIME` managed by Terraform/portal, not CI/CD

### Testing
- **Unit Tests**: Pytest for business logic
- **Integration Tests**: Cosmos DB emulator for local testing
- **Contract Tests**: Request/response validation
- **E2E Tests**: Full flow testing
- **Security Tests**: Auth, authorization, input validation
- **Load Testing**: Keep load testing minimal to preserve free tier quotas

## Performance Optimization

### Cold Start Mitigation
- **Lazy Loading**: Container and services loaded on first request, not at module import time
- **Minimize dependencies**: Only import what you need
- **TYPE_CHECKING imports**: Use `if TYPE_CHECKING:` for type-only imports
- **Reuse connections**: Cosmos DB client cached in module-level singleton

### Cosmos DB Performance
- **Partition key queries**: Always include partition key in queries
- **Point reads**: Use `read_item()` for single documents (fastest)
- **Query optimization**: Use indexes, avoid cross-partition queries
- **Batch operations**: Use bulk operations for multiple writes

### Request Optimization
- **Compression**: Enable gzip compression for responses
- **Pagination**: Support both sequential and parallel pagination patterns
- **Async operations**: Use async/await for I/O
- **Parallel operations**: Use asyncio.gather for independent operations

## Critical Implementation Guidelines

1. Use `ChainedTokenCredential` (ManagedIdentityCredential → AzureCliCredential) for fast cold starts
2. Authenticate with Cosmos DB using managed identity
3. Validate bearer tokens on every request
4. Enforce tenant isolation by filtering queries by user ID
5. Exclude sensitive data from logs (tokens, passwords, PII)
6. Implement rate limiting middleware
7. Handle exceptions with try-catch blocks and appropriate status codes
8. Use partition keys in all Cosmos DB queries
9. Paginate cross-partition queries
10. Use environment variables for all configuration
11. Implement audit logging via `MonitoringService.create_audit_log()`
12. Return generic error messages (no stack traces) in API responses
13. Use dependency injection container for all service instantiation
14. Keep cold start dependencies minimal
15. Test locally with Cosmos DB emulator before deployment
16. Use dataclasses with MyPy for request validation
17. Return direct objects with `X-Trace-Id` header
18. Let OpenTelemetry handle telemetry export automatically
19. Separate business logic from Azure Functions framework code

## Resources

- Azure Functions Python: https://learn.microsoft.com/en-us/azure/azure-functions/functions-reference-python
- Azure Cosmos DB SDK: https://learn.microsoft.com/en-us/azure/cosmos-db/nosql/sdk-python
- OpenTelemetry Python: https://opentelemetry.io/docs/languages/python/
- Grafana Cloud OTLP: https://grafana.com/docs/grafana-cloud/send-data/otlp/

## Success Criteria

Your backend API should:
1. ✅ Validate bearer tokens on every protected endpoint
2. ✅ Enforce tenant isolation by user ID in all database queries
3. ✅ Use managed identity for Cosmos DB authentication
4. ✅ Implement rate limiting per user
5. ✅ Log all actions to audit logs container
6. ✅ Return proper HTTP status codes and error messages
7. ✅ Handle all exceptions gracefully
8. ✅ Instrument with OpenTelemetry (traces and metrics)
9. ✅ Send structured logs to Grafana Loki
10. ✅ Have CI/CD pipeline that deploys dashboards to folder `slidesay-prod`
11. ✅ Be performant (p99 latency <500ms for simple queries)
12. ✅ Have high test coverage (>80%)
13. ✅ Follow Python and Azure Functions best practices
14. ✅ Use type hints and pass mypy checks
15. ✅ Be secure (no secrets in code, proper input validation)

## Final Notes

This is a production-grade serverless backend for a multi-tenant SaaS application. Security and tenant isolation are paramount. Every request must be authenticated, every query must be scoped to the authenticated user, and every action must be audited.

Focus on:
- **Security**: Token validation, tenant isolation, input validation, audit logging
- **Reliability**: Error handling, retry logic, rate limiting
- **Observability**: Distributed tracing, structured logging, metrics
- **Performance**: Partition key usage, cold start optimization, async operations
- **Maintainability**: Clean code, type hints, comprehensive tests

Build features incrementally, test thoroughly (including security tests), and monitor production closely. Your Cosmos DB containers use TTL for automatic cleanup (audit logs: 30 days, rate limits: 1 hour), so design with this in mind.
