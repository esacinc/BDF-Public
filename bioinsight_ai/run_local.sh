#!/bin/bash
set -euo pipefail

ENV=${1:-}

if [[ -z "$ENV" ]]; then
  echo "Usage: ./run_local.sh <local|dev|stage|prod>"
  exit 1
fi

APP_NAME="bdf-chatbot"
CONTAINER_NAME="${APP_NAME}-${ENV}"
ENV_FILE=".env.${ENV}"
IMAGE_NAME="${APP_NAME}:${ENV}"
BUILDX_BUILDER="local_builder"
CACHE_DIR="/tmp/buildx-cache"

# --- Verify env file ---
if [[ ! -f "$ENV_FILE" ]]; then
  echo "❌ ERROR: Missing environment file: ${ENV_FILE}"
  exit 1
fi

# --- Extract NEXT_PUBLIC_API_BASE ---
NEXT_PUBLIC_API_BASE=$(grep '^NEXT_PUBLIC_API_BASE=' "$ENV_FILE" | cut -d '=' -f2-)
if [[ -z "$NEXT_PUBLIC_API_BASE" ]]; then
  echo "❌ ERROR: NEXT_PUBLIC_API_BASE not found in $ENV_FILE"
  exit 1
fi

echo "🌍 Using NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE"

# --- Ensure Buildx builder exists ---
if ! docker buildx inspect "$BUILDX_BUILDER" >/dev/null 2>&1; then
  echo "🔧 Creating local Buildx builder: $BUILDX_BUILDER"
  docker buildx create --name "$BUILDX_BUILDER" --use
  docker buildx inspect --bootstrap
else
  echo "✅ Buildx builder '$BUILDX_BUILDER' already exists."
fi

# --- Stop any existing container ---
if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
  echo "🗑 Removing existing container: $CONTAINER_NAME"
  docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
fi

# --- Prepare cache directory ---
mkdir -p "$CACHE_DIR"

# --- Build with persistent local cache ---
echo "🐳 Building Docker image (cached): $IMAGE_NAME"
DOCKER_BUILDKIT=1 docker buildx build \
  --builder "$BUILDX_BUILDER" \
  --progress=plain \
  --build-arg NEXT_PUBLIC_API_BASE="$NEXT_PUBLIC_API_BASE" \
  --cache-from=type=local,src="$CACHE_DIR" \
  --cache-to=type=local,dest="$CACHE_DIR",mode=max \
  -t "$IMAGE_NAME" \
  --load .

# --- Dynamic port mapping ---
if [[ "$ENV" =~ ^(stage|prod)$ ]]; then
  PORT_MAPPING="80:80"
else
  PORT_MAPPING="8080:80"
fi

# --- Log driver setup ---
if [[ "$ENV" =~ ^(dev|stage)$ ]]; then
  LOG_DRIVER_OPTS=(
    "--log-driver=awslogs"
    "--log-opt" "awslogs-region=us-east-1"
    "--log-opt" "awslogs-group=/bdf-chatbot/$ENV"
    "--log-opt" "awslogs-stream=$CONTAINER_NAME"
  )
else
  LOG_DRIVER_OPTS=("--log-driver=json-file")
fi

echo "🐳 Using log driver: ${LOG_DRIVER_OPTS[0]}"

# --- Run container ---
echo "🚀 Running container: $CONTAINER_NAME"
docker run -d \
  --env-file "$ENV_FILE" \
  "${LOG_DRIVER_OPTS[@]}" \
  -p "$PORT_MAPPING" \
  --name "$CONTAINER_NAME" \
  --memory="7g" \
  --cpus="2.0" \
  "$IMAGE_NAME"

echo "✅ Container running at: http://localhost:${PORT_MAPPING%%:*}"

if [[ "${LOG_DRIVER_OPTS[0]}" == "json-file" ]]; then
  echo "📜 Logs: docker logs -f $CONTAINER_NAME"
else
  echo "📜 CloudWatch: /bdf-chatbot/$ENV"
fi

# --- Optional: Show cache size summary ---
echo "📦 Build cache size:"
du -sh "$CACHE_DIR" || true
