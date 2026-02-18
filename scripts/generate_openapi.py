#!/usr/bin/env python3
"""
OpenAPI Specification Generator for Azure Functions.

Generates OpenAPI 3.0 spec by introspecting the function app decorators
and endpoint service docstrings.

Usage:
    python scripts/generate_openapi.py

Output:
    openapi/openapi.json
    openapi/openapi.yaml (if PyYAML installed)
"""

import ast
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class EndpointInfo:
    """Information about an HTTP endpoint."""

    function_name: str
    route: str
    methods: list[str]
    summary: str
    description: str
    parameters: list[dict[str, Any]]
    request_body: dict[str, Any] | None
    responses: dict[str, dict[str, Any]]
    tags: list[str]


def extract_docstring_info(docstring: str | None) -> tuple[str, str, dict]:
    """
    Extract summary, description, and metadata from docstring.

    Returns:
        Tuple of (summary, description, metadata_dict)
    """
    if not docstring:
        return "", "", {}

    lines = docstring.strip().split("\n")
    summary = lines[0].strip()
    description_lines = []
    metadata: dict[str, Any] = {}

    in_description = True
    current_section: str | None = None
    section_content: list[str] = []

    for line in lines[1:]:
        stripped = line.strip()

        # Check for section headers
        if stripped.endswith(":") and stripped[:-1] in [
            "Args",
            "Returns",
            "Raises",
            "Query Parameters",
            "Request Body",
            "Rate Limited",
        ]:
            if current_section and section_content:
                metadata[current_section] = "\n".join(section_content)
            current_section = stripped[:-1]
            section_content = []
            in_description = False
        elif current_section:
            section_content.append(stripped)
        elif in_description and stripped:
            description_lines.append(stripped)

    if current_section and section_content:
        metadata[current_section] = "\n".join(section_content)

    return summary, " ".join(description_lines), metadata


def parse_function_decorators(source_code: str) -> list[EndpointInfo]:
    """Parse Azure Functions decorators from source code."""
    endpoints: list[EndpointInfo] = []

    tree = ast.parse(source_code)

    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) or isinstance(node, ast.FunctionDef):
            route_info: dict[str, Any] = {}
            function_name: str | None = None

            # Check decorators
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Call):
                    if isinstance(decorator.func, ast.Attribute):
                        attr_name = decorator.func.attr

                        if attr_name == "function_name":
                            for keyword in decorator.keywords:
                                if (
                                    keyword.arg == "name"
                                    and isinstance(keyword.value, ast.Constant)
                                    and isinstance(keyword.value.value, str)
                                ):
                                    function_name = keyword.value.value

                        elif attr_name == "route":
                            for keyword in decorator.keywords:
                                if keyword.arg is None:
                                    continue
                                if isinstance(keyword.value, ast.Constant):
                                    route_info[keyword.arg] = keyword.value.value
                                elif (
                                    isinstance(keyword.value, ast.List) and keyword.arg is not None
                                ):
                                    route_info[keyword.arg] = [
                                        elt.value
                                        for elt in keyword.value.elts
                                        if isinstance(elt, ast.Constant)
                                    ]

            if route_info.get("route"):
                docstring = ast.get_docstring(node)
                summary, description, metadata = extract_docstring_info(docstring)

                # Determine tags from route
                route = route_info.get("route", "")
                if "/" in route:
                    tag = route.split("/")[0]
                else:
                    tag = route

                # Parse parameters from route
                parameters = []
                path_params = re.findall(r"\{(\w+)\}", route)
                for param in path_params:
                    parameters.append(
                        {
                            "name": param,
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    )

                # Check for rate limiting in docstring
                rate_limited = "Rate Limited:" in (docstring or "")

                # Determine request body
                request_body = None
                methods = route_info.get("methods", ["GET"])
                if any(m in ["POST", "PUT", "PATCH"] for m in methods):
                    request_body = {
                        "required": True,
                        "content": {"application/json": {"schema": {"type": "object"}}},
                    }

                # Build responses
                responses = {
                    "200": {
                        "description": "Successful response",
                        "content": {"application/json": {"schema": {"type": "object"}}},
                    },
                    "401": {
                        "description": "Authentication required",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                            }
                        },
                    },
                }

                if rate_limited:
                    responses["429"] = {
                        "description": "Rate limit exceeded",
                        "headers": {
                            "Retry-After": {
                                "description": "Seconds until rate limit resets",
                                "schema": {"type": "integer"},
                            }
                        },
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                            }
                        },
                    }

                endpoints.append(
                    EndpointInfo(
                        function_name=function_name or node.name,
                        route=route,
                        methods=methods,
                        summary=summary or f"{node.name} endpoint",
                        description=description,
                        parameters=parameters,
                        request_body=request_body,
                        responses=responses,
                        tags=[tag] if tag else [],
                    )
                )

    return endpoints


def generate_openapi_spec(endpoints: list[EndpointInfo], info: dict) -> dict:
    """Generate OpenAPI 3.0 specification."""
    spec: dict[str, Any] = {
        "openapi": "3.0.3",
        "info": info,
        "servers": [
            {"url": "http://localhost:7071/api", "description": "Local development"},
            {"url": "https://{function_app}.azurewebsites.net/api", "description": "Production"},
        ],
        "paths": {},
        "components": {
            "schemas": {
                "ErrorResponse": {
                    "type": "object",
                    "properties": {
                        "error": {
                            "type": "object",
                            "properties": {
                                "code": {
                                    "type": "string",
                                    "description": "Machine-readable error code",
                                    "example": "VALIDATION_ERROR",
                                },
                                "message": {
                                    "type": "string",
                                    "description": "Human-readable error message",
                                    "example": "Invalid input data",
                                },
                            },
                            "required": ["code", "message"],
                        }
                    },
                    "required": ["error"],
                },
                "User": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": "User ID"},
                        "email": {"type": "string", "format": "email"},
                        "displayName": {"type": "string"},
                        "createdAt": {"type": "string", "format": "date-time"},
                        "updatedAt": {"type": "string", "format": "date-time"},
                    },
                },
                "HealthStatus": {
                    "type": "object",
                    "properties": {
                        "status": {
                            "type": "string",
                            "enum": ["healthy", "degraded", "unhealthy"],
                        },
                        "version": {"type": "string"},
                        "database": {
                            "type": "string",
                            "enum": ["connected", "disconnected"],
                        },
                    },
                },
            },
            "securitySchemes": {
                "BearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT",
                    "description": "Microsoft Entra ID access token",
                }
            },
        },
        "security": [{"BearerAuth": []}],
        "tags": [],
    }

    # Collect unique tags
    tags_seen: set[str] = set()

    for endpoint in endpoints:
        path = f"/{endpoint.route}"

        if path not in spec["paths"]:
            spec["paths"][path] = {}

        for method in endpoint.methods:
            method_lower = method.lower()

            operation: dict[str, Any] = {
                "summary": endpoint.summary,
                "description": endpoint.description,
                "operationId": endpoint.function_name,
                "tags": endpoint.tags,
                "responses": endpoint.responses,
            }

            if endpoint.parameters:
                operation["parameters"] = endpoint.parameters

            if endpoint.request_body:
                operation["requestBody"] = endpoint.request_body

            # Health check doesn't require auth
            if endpoint.route == "health":
                operation["security"] = []

            spec["paths"][path][method_lower] = operation

            for tag in endpoint.tags:
                if tag not in tags_seen:
                    tags_seen.add(tag)
                    spec["tags"].append(
                        {"name": tag, "description": f"{tag.capitalize()} endpoints"}
                    )

    return spec


def main() -> int:
    """Main entry point."""
    # Find project root
    script_dir = Path(__file__).parent
    project_root = script_dir.parent

    # Read http_functions.py
    http_functions_path = project_root / "src" / "functions" / "http_functions.py"

    if not http_functions_path.exists():
        print(f"Error: {http_functions_path} not found")
        return 1

    source_code = http_functions_path.read_text()

    # Parse endpoints
    endpoints = parse_function_decorators(source_code)

    if not endpoints:
        print("Warning: No endpoints found in http_functions.py")

    # Generate OpenAPI spec
    info = {
        "title": "Backend API",
        "description": "REST API for the backend application. All endpoints (except health) require authentication via Microsoft Entra ID bearer token.",
        "version": "1.0.0",
        "contact": {"name": "API Support"},
        "license": {"name": "MIT"},
    }

    spec = generate_openapi_spec(endpoints, info)

    # Write JSON output
    openapi_dir = project_root / "openapi"
    openapi_dir.mkdir(exist_ok=True)

    json_path = openapi_dir / "openapi.json"
    with open(json_path, "w") as f:
        json.dump(spec, f, indent=2)
    print(f"Generated: {json_path}")

    # Try to write YAML if PyYAML is available
    try:
        import yaml  # type: ignore[import-untyped]

        yaml_path = openapi_dir / "openapi.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump(spec, f, sort_keys=False, default_flow_style=False)
        print(f"Generated: {yaml_path}")
    except ImportError:
        print("Note: Install PyYAML (pip install pyyaml) for YAML output")

    print(f"\nFound {len(endpoints)} endpoints:")
    for ep in endpoints:
        methods = ", ".join(ep.methods)
        print(f"  [{methods}] /{ep.route} -> {ep.function_name}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
