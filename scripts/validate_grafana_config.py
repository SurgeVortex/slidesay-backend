#!/usr/bin/env python3
"""
Validate Grafana dashboard and alert configuration files.
"""

import json
import sys
from pathlib import Path


def validate_dashboard(file_path: Path) -> bool:
    """Validate a Grafana dashboard JSON file."""
    try:
        with open(file_path) as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in {file_path}: {e}")
        return False

    errors = []

    # Check if it's a dashboard
    if "dashboard" in config:
        dashboard = config["dashboard"]

        # Required dashboard fields
        required_fields = ["title", "panels"]
        for field in required_fields:
            if field not in dashboard:
                errors.append(f"Missing required dashboard field: {field}")

        # Check panels
        panels = dashboard.get("panels", [])
        if not panels:
            errors.append("Dashboard has no panels")

        for i, panel in enumerate(panels):
            if "id" not in panel:
                errors.append(f"Panel {i} missing required 'id' field")
            if "title" not in panel:
                errors.append(f"Panel {i} missing required 'title' field")
            if "type" not in panel:
                errors.append(f"Panel {i} missing required 'type' field")

    # Check if it's an alert
    elif "alert" in config:
        alert = config["alert"]

        # Required alert fields
        required_fields = ["name", "conditions"]
        for field in required_fields:
            if field not in alert:
                errors.append(f"Missing required alert field: {field}")

        # Check conditions
        conditions = alert.get("conditions", [])
        if not conditions:
            errors.append("Alert has no conditions")

    else:
        errors.append("File is neither a dashboard nor an alert configuration")

    if errors:
        print(f"ERRORS in {file_path}:")
        for error in errors:
            print(f"  - {error}")
        return False

    print(f"✓ {file_path} is valid")
    return True


def main() -> None:
    """Main function to validate Grafana configuration files."""
    print("Validating Grafana configuration files...")

    grafana_dir = Path("grafana")
    if not grafana_dir.exists():
        print("ERROR: grafana directory not found")
        sys.exit(1)

    all_valid = True

    # Check dashboard files
    dashboard_dir = grafana_dir / "dashboards"
    if dashboard_dir.exists():
        for json_file in dashboard_dir.glob("*.json"):
            if not validate_dashboard(json_file):
                all_valid = False

    # Check alert files
    alert_dir = grafana_dir / "alerts"
    if alert_dir.exists():
        for json_file in alert_dir.glob("*.json"):
            if not validate_dashboard(json_file):  # Same validation logic
                all_valid = False

    if all_valid:
        print("\n✓ All Grafana configuration files are valid")
        sys.exit(0)
    else:
        print("\n✗ Grafana configuration has issues")
        sys.exit(1)


if __name__ == "__main__":
    main()
