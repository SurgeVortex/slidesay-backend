#!/usr/bin/env python3
"""
Grafana Dashboard and Alert Sync Script

Uploads dashboards and alert rules to Grafana Cloud.
Used by CI/CD workflow and can be run manually for testing.
"""

import json
import os
import sys
from pathlib import Path

import requests


def upload_dashboards(grafana_url: str, api_key: str) -> tuple[int, int]:
    """
    Upload all dashboards to Grafana.

    Args:
        grafana_url: Grafana instance URL
        api_key: Grafana API key

    Returns:
        Tuple of (success_count, error_count)
    """
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    dashboards_dir = Path("grafana/dashboards")
    if not dashboards_dir.exists():
        print("No dashboards directory found, skipping")
        return 0, 0

    success_count = 0
    error_count = 0

    for dashboard_file in dashboards_dir.glob("*.json"):
        print(f"Uploading dashboard: {dashboard_file.name}")

        try:
            with open(dashboard_file) as f:
                dashboard_json = json.load(f)

            payload = {
                "dashboard": dashboard_json,
                "overwrite": True,
                "message": f"Updated via CI/CD - {os.environ.get('GITHUB_SHA', 'manual')[:7]}",
            }

            response = requests.post(
                f"{grafana_url}/api/dashboards/db", headers=headers, json=payload, timeout=10
            )

            if response.status_code in (200, 201):
                print(f"✓ Successfully uploaded {dashboard_file.name}")
                success_count += 1
            else:
                print(f"✗ Failed to upload {dashboard_file.name}: {response.status_code}")
                print(f"  Response: {response.text}")
                error_count += 1

        except Exception as e:
            print(f"✗ Error uploading {dashboard_file.name}: {str(e)}")
            error_count += 1

    return success_count, error_count


def upload_alerts(grafana_url: str, api_key: str) -> tuple[int, int]:
    """
    Upload all alert rules to Grafana.

    Args:
        grafana_url: Grafana instance URL
        api_key: Grafana API key

    Returns:
        Tuple of (success_count, error_count)
    """
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    alerts_dir = Path("grafana/alerts")
    if not alerts_dir.exists():
        print("No alerts directory found, skipping")
        return 0, 0

    success_count = 0
    error_count = 0

    for alert_file in alerts_dir.glob("*.json"):
        print(f"Uploading alert rule: {alert_file.name}")

        try:
            with open(alert_file) as f:
                alert_json = json.load(f)

            response = requests.post(
                f"{grafana_url}/api/v1/provisioning/alert-rules",
                headers=headers,
                json=alert_json,
                timeout=10,
            )

            if response.status_code in (200, 201, 202):
                print(f"✓ Successfully uploaded {alert_file.name}")
                success_count += 1
            else:
                print(f"✗ Failed to upload {alert_file.name}: {response.status_code}")
                print(f"  Response: {response.text}")
                error_count += 1

        except Exception as e:
            print(f"✗ Error uploading {alert_file.name}: {str(e)}")
            error_count += 1

    return success_count, error_count


def main() -> None:
    """Main entry point."""
    grafana_url = os.environ.get("GRAFANA_CLOUD_URL")
    # Support either GRAFANA_CLOUD_API_KEY or GRAFANA_CLOUD_MANAGEMENT_TOKEN (terraform naming)
    api_key = os.environ.get("GRAFANA_CLOUD_API_KEY") or os.environ.get(
        "GRAFANA_CLOUD_MANAGEMENT_TOKEN"
    )

    if not grafana_url or not api_key:
        print("Skipping Grafana sync: GRAFANA_CLOUD_URL or Grafana API key not set")
        # For template repos we don't treat missing Grafana credentials as fatal.
        # This allows clones to build and deploy without requiring Grafana secrets.
        return

    print("=" * 60)
    print("Grafana Dashboard and Alert Sync")
    print("=" * 60)

    # Upload dashboards
    print("\nUploading dashboards...")
    dash_success, dash_errors = upload_dashboards(grafana_url, api_key)
    print(f"Dashboards: {dash_success} successful, {dash_errors} failed")

    # Upload alerts
    print("\nUploading alert rules...")
    alert_success, alert_errors = upload_alerts(grafana_url, api_key)
    print(f"Alerts: {alert_success} successful, {alert_errors} failed")

    # Summary
    print("\n" + "=" * 60)
    total_success = dash_success + alert_success
    total_errors = dash_errors + alert_errors
    print(f"Total: {total_success} successful, {total_errors} failed")
    print("=" * 60)

    if total_errors > 0:
        sys.exit(1)

    print("\n✅ All Grafana configurations synced successfully")


if __name__ == "__main__":
    main()
