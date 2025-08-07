#!/bin/sh

set -e  # Exit immediately on error

echo "Launching BDF-Chatbot in $APP_ENV mode..."

# Print Python and Chainlit version
echo "Python path: $(which python)"
echo "Python version: $(python --version)"
echo "Chainlit version: $(chainlit --version 2>/dev/null || echo 'Chainlit not found')"

# Check disk usage and fail if > 95%
USAGE=$(df / | awk 'END {print $5}' | sed 's/%//')
if [ "$USAGE" -ge 95 ]; then
  echo "Disk usage is ${USAGE}%. Exiting."
  exit 1
fi

CMD="chainlit run chainlit_app.py --host 0.0.0.0 --port 8000"

case "$APP_ENV" in
  local|dev|stage|prod)
    echo "Starting Chainlit with command: $CMD"
    exec sh -c "$CMD"
    ;;
  *)
    echo "Invalid APP_ENV: $APP_ENV"
    exit 1
    ;;
esac
