#!/usr/bin/env python3
"""
Check Azure Function configuration files for required settings.
"""

import json
import sys
from pathlib import Path


def check_host_json() -> bool:
    """Check host.json for required Azure Functions settings."""
    host_json_path = Path("host.json")

    if not host_json_path.exists():
        print("ERROR: host.json not found")
        return False

    try:
        with open(host_json_path) as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in host.json: {e}")
        return False

    required_settings: dict[str, str | dict[str, str]] = {
        "version": "2.0",
        "extensionBundle": {
            "id": "Microsoft.Azure.Functions.ExtensionBundle",
            "version": "[4.*, 5.0.0)",
        },
    }

    errors: list[str] = []

    # Check version
    if config.get("version") != required_settings["version"]:
        errors.append(f"host.json version should be '{required_settings['version']}'")

    # Check extension bundle
    bundle = config.get("extensionBundle", {})
    expected_bundle_id = "Microsoft.Azure.Functions.ExtensionBundle"
    expected_bundle_version = "[4.*, 5.0.0)"

    if bundle.get("id") != expected_bundle_id:
        errors.append(f"Extension bundle ID should be '{expected_bundle_id}'")

    if bundle.get("version") != expected_bundle_version:
        errors.append(f"Extension bundle version should be '{expected_bundle_version}'")

    # Check for recommended settings
    recommendations = []

    if "functionTimeout" not in config:
        recommendations.append("Consider setting functionTimeout")

    if "logging" not in config:
        recommendations.append("Consider configuring logging settings")

    if "retry" not in config:
        recommendations.append("Consider configuring retry policy")

    if errors:
        print("ERRORS in host.json:")
        for error in errors:
            print(f"  - {error}")
        return False

    if recommendations:
        print("RECOMMENDATIONS for host.json:")
        for rec in recommendations:
            print(f"  - {rec}")

    print("✓ host.json configuration is valid")
    return True


def check_local_settings_template() -> bool:
    """Check local.settings.json.template for required settings."""
    template_path = Path("local.settings.json.template")

    if not template_path.exists():
        print("ERROR: local.settings.json.template not found")
        return False

    try:
        with open(template_path) as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in local.settings.json.template: {e}")
        return False

    required_values = [
        "AzureWebJobsStorage",
        "FUNCTIONS_WORKER_RUNTIME",
        "FUNCTIONS_EXTENSION_VERSION",
        "APP_NAME",
        "COSMOSDB_ENDPOINT",
        "COSMOSDB_DATABASE_NAME",
    ]

    values = config.get("Values", {})
    errors = []

    for required in required_values:
        if required not in values:
            errors.append(f"Missing required setting: {required}")
        elif not values[required]:
            errors.append(f"Empty value for required setting: {required}")

    # Check specific values
    if values.get("FUNCTIONS_WORKER_RUNTIME") != "python":
        errors.append("FUNCTIONS_WORKER_RUNTIME should be 'python'")

    if values.get("FUNCTIONS_EXTENSION_VERSION") != "~4":
        errors.append("FUNCTIONS_EXTENSION_VERSION should be '~4'")

    if errors:
        print("ERRORS in local.settings.json.template:")
        for error in errors:
            print(f"  - {error}")
        return False

    print("✓ local.settings.json.template configuration is valid")
    return True


def main() -> None:
    """Main function to check Azure Function settings."""
    print("Checking Azure Function configuration files...")

    host_valid = check_host_json()
    template_valid = check_local_settings_template()

    if host_valid and template_valid:
        print("\n✓ All Azure Function configuration files are valid")
        sys.exit(0)
    else:
        print("\n✗ Azure Function configuration has issues")
        sys.exit(1)


if __name__ == "__main__":
    main()
