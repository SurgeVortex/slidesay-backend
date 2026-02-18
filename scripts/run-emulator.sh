#!/usr/bin/env bash
set -euo pipefail

IMAGE=${1:-mcr.microsoft.com/cosmosdb/linux/azure-cosmos-emulator:vnext-preview}
CONTAINER_NAME=${2:-cosmos-emulator}

echo "Starting Cosmos DB emulator (image=${IMAGE})..."

docker run -d --name "${CONTAINER_NAME}" -p 8081:8081 "${IMAGE}"

echo "Waiting for emulator to be ready (timeout 300s)..."
timeout 300 bash -c "until curl -k -f https://localhost:8081/_explorer/emulator.pem; do sleep 5; done"

echo "Cosmos emulator is ready at https://localhost:8081"
