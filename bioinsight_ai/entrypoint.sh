#!/bin/sh

set -e  # Exit immediately on error

echo "Launching BDF-Chatbot in $APP_ENV mode..."

# Print versions
echo "Python path: $(which python)"
echo "Python version: $(python --version)"
echo "Chainlit version: $(chainlit --version 2>/dev/null || echo 'Chainlit not found')"

# ✅ Disable Chainlit's built-in authentication
export CHAINLIT_AUTH_DISABLE=true

# Check disk usage and fail if > 95%
USAGE=$(df / | awk 'END {print $5}' | sed 's/%//')
if [ "$USAGE" -ge 95 ]; then
  echo "Disk usage is ${USAGE}%. Exiting."
  exit 1
fi

case "$APP_ENV" in
  local|dev|stage|prod)
    echo "Starting services..."

    # ✅ Always start Chainlit behind /chat
    echo "➡️  Starting Chainlit with root-path /chat"
    chainlit run chainlit_app.py --host 0.0.0.0 --port 8000 --root-path /chat &
    CHAINLIT_PID=$!

    # Start FastAPI (auth backend)
    uvicorn web_auth.main:app --host 0.0.0.0 --port 7000 &
    FASTAPI_PID=$!

    # Start Next.js frontend
    cd frontend && npm run start -- -p 3000 &
    NEXT_PID=$!
    cd ..

    # Start Nginx reverse proxy
    nginx -g 'daemon off;' &
    NGINX_PID=$!

    # Trap signals and shut down all services cleanly
    trap "echo 'Stopping services...'; kill $CHAINLIT_PID $FASTAPI_PID $NEXT_PID $NGINX_PID; exit 0" TERM INT

    # Manual wait loop (POSIX-friendly)
    while true; do
      if ! kill -0 $CHAINLIT_PID 2>/dev/null; then
        echo "Chainlit process exited"
        break
      fi
      if ! kill -0 $FASTAPI_PID 2>/dev/null; then
        echo "FastAPI process exited"
        break
      fi
      if ! kill -0 $NEXT_PID 2>/dev/null; then
        echo "Next.js process exited"
        break
      fi
      if ! kill -0 $NGINX_PID 2>/dev/null; then
        echo "Nginx process exited"
        break
      fi
      sleep 2
    done

    kill $CHAINLIT_PID $FASTAPI_PID $NEXT_PID $NGINX_PID
    exit 1
    ;;
  *)
    echo "Invalid APP_ENV: $APP_ENV"
    exit 1
    ;;
esac
