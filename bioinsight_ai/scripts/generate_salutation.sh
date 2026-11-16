#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/home/ubuntu/BDF-Chatbot"
ENV_FILE="${APP_DIR}/.env.runtime"

# Extract DEPLOY_ENV same way start_server.sh does
DEPLOY_ENV=$(grep -E '^DEPLOY_ENV=' "$ENV_FILE" | cut -d '=' -f2 | tr -d '"')

# Container name matches start_server.sh naming convention
CONTAINER_NAME="bdf-chatbot-${DEPLOY_ENV}"

echo "[CodeDeploy] Generating BioInsight opening message in container: $CONTAINER_NAME"

# Ensure container is running
if ! docker ps --format '{{.Names}}' | grep -q "$CONTAINER_NAME"; then
  echo "[CodeDeploy] Container '$CONTAINER_NAME' is not running. Skipping."
  exit 0
fi

# Execute Python script inside container using venv
docker exec "$CONTAINER_NAME" \
  /opt/venv/bin/python -m integrations.chainlit.on_chat_start.opening_message || {
    echo "[CodeDeploy] ⚠️ Salutation generation failed (ignored)."
  }

echo "[CodeDeploy] Salutation generation completed."
