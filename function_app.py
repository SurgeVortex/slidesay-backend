"""
Azure Functions Entry Point (Ultra-thin Wrapper)

This file exists ONLY because Azure Functions Python v2 requires
a file named `function_app.py` at the package root.

All actual function definitions and business logic live in:
- src/functions/http_functions.py  (Azure Functions adapters)
- src/services/endpoint_service.py (business logic)
- src/container.py (dependency injection)

This separation allows:
- Tests to import from src.* without Azure Functions runtime
- Local development with `func start` to work correctly
- Future framework migrations (FastAPI, Flask) without touching this file
"""

from src.functions import app  # noqa: F401

# Re-export the FunctionApp instance for Azure Functions runtime discovery
# The runtime will find `app` and register all decorated functions
