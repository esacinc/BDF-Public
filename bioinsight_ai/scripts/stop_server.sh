#!/bin/bash
set -e

APP_NAME="bdf-chatbot"
APP_DIR="/home/ubuntu/BDF-Chatbot"
ENV_FILE="${APP_DIR}/.env.runtime"

echo ">> [ApplicationStop] Stopping and removing Docker container..."

if [ ! -f "$ENV_FILE" ]; then
  echo ">> [ApplicationStop] .env.runtime not found. Skipping container stop."
  exit 0
fi

DEPLOY_ENV=$(grep -E '^DEPLOY_ENV=' "$ENV_FILE" | cut -d '=' -f2 | tr -d '"')
CONTAINER_NAME="${APP_NAME}-${DEPLOY_ENV}"

docker stop "$CONTAINER_NAME" 2>/dev/null || echo "No container to stop"
docker rm "$CONTAINER_NAME" 2>/dev/null || echo "No container to remove"

echo ">> [ApplicationStop] Pruning Docker system..."
docker system prune -af --volumes || true

echo ">> [ApplicationStop] Cleanup complete."
