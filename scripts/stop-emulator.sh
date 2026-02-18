#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME=${1:-cosmos-emulator}

echo "Stopping and removing container ${CONTAINER_NAME}..."
docker rm -f "${CONTAINER_NAME}" || true

echo "Stopped."
