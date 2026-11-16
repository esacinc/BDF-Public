#!/bin/bash
set -e

APP_DIR="/home/ubuntu/BDF-Chatbot"

echo ">> [BeforeInstall] Cleaning existing contents of ${APP_DIR}..."

if [ -d "$APP_DIR" ]; then
  echo ">> Directory exists. Listing before cleanup:"
  ls -la "$APP_DIR"

  echo ">> Deleting files and folders..."
  sudo rm -rf "${APP_DIR:?}/"* "${APP_DIR}/".* 2>/dev/null || true

  echo ">> Listing after cleanup:"
  ls -la "$APP_DIR"
else
  echo ">> Directory does not exist. Creating..."
  mkdir -p "$APP_DIR"
  sudo chown ubuntu:ubuntu "$APP_DIR"
fi

echo ">> Cleanup complete."
