# OpenAPI Specification

This directory contains auto-generated OpenAPI (Swagger) specifications for the backend API.

## Files

- `openapi.json` - OpenAPI 3.0 specification in JSON format
- `openapi.yaml` - OpenAPI 3.0 specification in YAML format (if PyYAML installed)

## Generating the Specification

```bash
make openapi
```

Or directly:

```bash
python scripts/generate_openapi.py
```

## How It Works

The generator parses `src/functions/http_functions.py` and extracts:

1. **Route decorators** - `@app.route(route="...", methods=["..."])`
2. **Function names** - `@app.function_name(name="...")`
3. **Docstrings** - Used for summary and description

The generator automatically:

- Extracts path parameters from route patterns like `{id}`
- Adds authentication requirements (Bearer token)
- Includes rate limiting headers for documented endpoints
- Generates error response schemas

## Adding Endpoint Documentation

To improve the generated documentation, add detailed docstrings:

```python
@app.function_name(name="list_items")
@app.route(route="items", methods=["GET"], auth_level=AuthLevel.ANONYMOUS)
async def list_items(req: func.HttpRequest) -> func.HttpResponse:
    """
    List all items for the authenticated user.

    Returns a paginated list of items owned by the current user.

    Query Parameters:
        page (int): Page number, default 1
        pageSize (int): Items per page, default 20, max 100

    Rate Limited: 100 requests per minute
    """
    ...
```

## Using the Specification

### Import into Postman

1. Open Postman
2. Import → File → Select `openapi.json`
3. Postman creates a collection with all endpoints

### Generate Client SDKs

```bash
# Using OpenAPI Generator
npx @openapitools/openapi-generator-cli generate \
  -i openapi/openapi.json \
  -g typescript-fetch \
  -o generated-client/
```

### View in Swagger UI

```bash
# Start local Swagger UI with Docker
docker run -p 8080:8080 \
  -e SWAGGER_JSON=/openapi/openapi.json \
  -v $(pwd)/openapi:/openapi \
  swaggerapi/swagger-ui
```

Then open <http://localhost:8080>

## Extending the Generator

The generator is in `scripts/generate_openapi.py`. To add custom schemas:

1. Edit the `components.schemas` section in `generate_openapi_spec()`
2. Reference your schema in endpoint responses

Example:

```python
"components": {
    "schemas": {
        "Item": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "name": {"type": "string"},
                "createdAt": {"type": "string", "format": "date-time"}
            }
        }
    }
}
```
