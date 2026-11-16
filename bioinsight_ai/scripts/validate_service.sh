#!/bin/bash

APP_NAME="bdf-chatbot"
ENV_FILE="/home/ubuntu/BDF-Chatbot/.env.runtime"

echo "[validate_service] $(date) >> Validating '${APP_NAME}' container health..."

# --- Check if env file exists ---
if [ ! -f "$ENV_FILE" ]; then
  echo "[validate_service] ERROR: .env.runtime not found at $ENV_FILE"
  exit 1
fi

# --- Extract DEPLOY_ENV ---
DEPLOY_ENV=$(grep -E '^DEPLOY_ENV=' "$ENV_FILE" | cut -d '=' -f2 | tr -d '"')
if [[ -z "$DEPLOY_ENV" ]]; then
  echo "[validate_service] ERROR: DEPLOY_ENV not set properly"
  exit 1
fi

CONTAINER_NAME="${APP_NAME}-${DEPLOY_ENV}"

# Stage/prod → port 80, local/dev → port 8080
if [[ "$DEPLOY_ENV" == "stage" || "$DEPLOY_ENV" == "prod" ]]; then
  APP_PORT=80
else
  APP_PORT=8080
fi

FRONTEND_URL="http://localhost:${APP_PORT}/chat/"
FASTAPI_HEALTH_URL="http://localhost:${APP_PORT}/api/auth/verify"
CHAINLIT_HEALTH_URL="http://localhost:${APP_PORT}/chat/"

echo "[validate_service] >> Environment: ${DEPLOY_ENV}"
echo "[validate_service] >> Frontend check: ${FRONTEND_URL}"
echo "[validate_service] >> FastAPI health check: ${FASTAPI_HEALTH_URL}"
echo "[validate_service] >> Chainlit health check: ${CHAINLIT_HEALTH_URL}"

# --- Check Docker container status ---
RUNNING=$(docker ps --filter "name=${CONTAINER_NAME}" --filter "status=running" -q)
if [[ -z "$RUNNING" ]]; then
  echo "[validate_service] ERROR: Docker container '${CONTAINER_NAME}' is NOT running."
  docker ps -a
  exit 1
fi

echo "[validate_service] Docker container '${CONTAINER_NAME}' is running."

# --- Print recent logs ---
echo "[validate_service] >> Last 10 lines of container logs:"
docker logs "$CONTAINER_NAME" 2>&1 | tail -n 10 || echo "[validate_service] (No logs found)"

# --- Helper function with expected codes ---
check_service() {
  local name=$1
  local url=$2
  local ok_codes=$3
  echo "[validate_service] >> Checking $name..."
  for i in {1..20}; do
    HTTP_RESPONSE=$(curl -s -o /tmp/validate_body.$$ -w "%{http_code}" --max-time 10 "$url")
    if [[ " $ok_codes " == *" $HTTP_RESPONSE "* ]]; then
      BODY=$(cat /tmp/validate_body.$$)
      echo "[validate_service] ✅ $name is up (HTTP $HTTP_RESPONSE at $url)"
      echo "[validate_service] >> Response body (truncated): $(echo "$BODY" | head -c 200)"
      rm -f /tmp/validate_body.$$
      return 0
    else
      echo "[validate_service] Attempt $i: $name not ready (HTTP $HTTP_RESPONSE). Retrying in 3s..."
      sleep 3
    fi
  done
  echo "[validate_service] ❌ $name failed health check"
  rm -f /tmp/validate_body.$$
  return 1
}

# --- Perform checks with per-service codes ---
check_service "Next.js frontend" "$FRONTEND_URL" "200 302" || FRONTEND_FAIL=true
check_service "FastAPI backend" "$FASTAPI_HEALTH_URL" "200 401" || FASTAPI_FAIL=true
check_service "Chainlit backend" "$CHAINLIT_HEALTH_URL" "200 302" || CHAINLIT_FAIL=true

# --- Final result ---
if [[ -z "$FRONTEND_FAIL" && -z "$FASTAPI_FAIL" && -z "$CHAINLIT_FAIL" ]]; then
  echo "[validate_service] ✅ All services healthy"
  exit 0
else
  echo "[validate_service] ❌ One or more services unhealthy"
  exit 1
fi
