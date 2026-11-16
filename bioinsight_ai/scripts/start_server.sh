#!/bin/bash
set -e

APP_NAME="bdf-chatbot"
APP_DIR="/home/ubuntu/BDF-Chatbot"
ENV_FILE="${APP_DIR}/.env.runtime"
LOG_DIR="${APP_DIR}/logs"
LOG_FILE="${LOG_DIR}/${APP_NAME}.log"

# Ensure log directory exists for deploy logs (not app logs)
mkdir -p "$LOG_DIR"

echo ">> Starting ${APP_NAME} deployment at $(date)" | tee -a "$LOG_FILE"

# Validate .env.runtime exists
if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: Missing ${ENV_FILE}" | tee -a "$LOG_FILE"
  exit 1
fi

# Extract DEPLOY_ENV from .env.runtime
DEPLOY_ENV=$(grep -E '^DEPLOY_ENV=' "$ENV_FILE" | cut -d '=' -f2 | tr -d '"')
if [[ -z "$DEPLOY_ENV" ]]; then
  echo "ERROR: DEPLOY_ENV not set in ${ENV_FILE}" | tee -a "$LOG_FILE"
  exit 1
fi

# Define Docker image & container based on environment
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION=$(grep -E '^AWS_REGION=' "$ENV_FILE" | cut -d '=' -f2 | tr -d '"')
ECR_REPO="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${APP_NAME}-${DEPLOY_ENV}"
IMAGE_TAG="latest"
IMAGE_NAME="${ECR_REPO}:${IMAGE_TAG}"
CONTAINER_NAME="${APP_NAME}-${DEPLOY_ENV}"

# Port mapping: Nginx handles all, expose 80
if [[ "$DEPLOY_ENV" == "stage" || "$DEPLOY_ENV" == "prod" ]]; then
  PORT_MAPPING="80:80"
else
  PORT_MAPPING="8080:80"
fi

echo ">> Environment: $DEPLOY_ENV"
echo ">> Docker image: $IMAGE_NAME"
echo ">> Port mapping: $PORT_MAPPING"

# Stop & remove existing container if any
echo ">> Cleaning up old container (if exists)..."
docker stop "$CONTAINER_NAME" 2>/dev/null || true
docker rm "$CONTAINER_NAME" 2>/dev/null || true

# Login to ECR
echo ">> Logging into ECR..."
aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$ECR_REPO"

# Pull latest image
echo ">> Pulling image: $IMAGE_NAME"
docker pull "$IMAGE_NAME"

# Decide log driver
if [[ "$DEPLOY_ENV" == "dev" || "$DEPLOY_ENV" == "stage" || "$DEPLOY_ENV" == "prod" ]]; then
  LOG_DRIVER="awslogs"
  LOG_OPTS="--log-driver=awslogs \
    --log-opt awslogs-region=$AWS_REGION \
    --log-opt awslogs-group=/bdf-chatbot/$DEPLOY_ENV \
    --log-opt awslogs-stream=$CONTAINER_NAME"
else
  LOG_DRIVER="json-file"
  LOG_OPTS="--log-driver=json-file"
fi

echo ">> Using log driver: $LOG_DRIVER"

# Resource limits
MEMORY_LIMIT="7g"
CPU_LIMIT="2"
# Run container
echo ">> Running container: $CONTAINER_NAME"
docker run -d \
  --name "$CONTAINER_NAME" \
  --env-file "$ENV_FILE" \
  $LOG_OPTS \
  --memory "$MEMORY_LIMIT" \
  --cpus "$CPU_LIMIT" \
  --restart unless-stopped \
  -p "$PORT_MAPPING" \
  "$IMAGE_NAME" >> "$LOG_FILE" 2>&1

if [ $? -eq 0 ]; then
  echo ">> Container started successfully: $CONTAINER_NAME" | tee -a "$LOG_FILE"
else
  echo "ERROR: Failed to start container" | tee -a "$LOG_FILE"
  exit 1
fi

exit 0
