#!/usr/bin/env bash

# Run Percy visual regression snapshots against the static Next.js export.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WEB_DIR="$ROOT_DIR/src/web"
PORT="${PERCY_PREVIEW_PORT:-4183}"

if [ -z "${PERCY_TOKEN:-}" ]; then
    echo "❌ PERCY_TOKEN is not set. Visual snapshots require a Percy project token."
    exit 1
fi

echo "▶ Building Next.js application..."
(cd "$WEB_DIR" && npm run build >/dev/null)

echo "▶ Starting Next.js server on port ${PORT}..."
(cd "$WEB_DIR" && PORT="$PORT" npm run start >/tmp/percy-next-server.log 2>&1) &
SERVER_PID=$!

# Wait for the server to come online (max 30s)
ATTEMPTS=0
until curl -sSf "http://localhost:${PORT}" >/dev/null 2>&1; do
    ATTEMPTS=$((ATTEMPTS + 1))
    if [ "$ATTEMPTS" -ge 30 ]; then
        echo "❌ Next.js server did not become ready on port ${PORT} (see /tmp/percy-next-server.log)."
        exit 1
    fi
    sleep 1
done

cleanup() {
    if ps -p $SERVER_PID >/dev/null 2>&1; then
        kill $SERVER_PID
    fi
}
trap cleanup EXIT

echo "▶ Capturing Percy snapshots..."
(cd "$WEB_DIR" && npx percy snapshot percy-snapshots.yml --base-url "http://localhost:${PORT}")

echo "✅ Visual regression snapshots complete."
