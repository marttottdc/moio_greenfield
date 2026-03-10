#!/usr/bin/env bash
# Create test tenant via self-provision API (async, polls until done).
# Usage: ./scripts/create_test_tenant.sh [BASE_URL]
# Default BASE_URL: http://127.0.0.1:8093
# Requires: Celery worker running.

set -e
BASE_URL="${1:-http://127.0.0.1:8093}"

echo "Creating test tenant at $BASE_URL..."

RESP=$(curl -s -X POST "$BASE_URL/api/v1/tenants/self-provision/" \
  -H "Content-Type: application/json" \
  -d '{
    "nombre": "Test Tenant",
    "subdomain": "test",
    "domain": "127.0.0.1",
    "email": "test@moio.ai",
    "username": "test@moio.ai",
    "password": "test123",
    "first_name": "Test",
    "last_name": "Admin"
  }')

TASK_ID=$(echo "$RESP" | grep -o '"task_id":"[^"]*"' | cut -d'"' -f4)
if [ -z "$TASK_ID" ]; then
  echo "Error: $RESP"
  exit 1
fi

echo "Task queued: $TASK_ID. Polling..."
for i in {1..60}; do
  STATUS_RESP=$(curl -s "$BASE_URL/api/v1/tenants/provision-status/$TASK_ID/")
  STATUS=$(echo "$STATUS_RESP" | grep -o '"status":"[^"]*"' | head -1 | cut -d'"' -f4)
  if [ "$STATUS" = "success" ]; then
    echo "OK: Test tenant created."
    echo "Credentials: test@moio.ai / test123"
    echo "See backend/docs/TEST_TENANT.md for full documentation."
    exit 0
  fi
  if [ "$STATUS" = "failure" ]; then
    echo "Error: $STATUS_RESP"
    exit 1
  fi
  sleep 2
done
echo "Timeout waiting for provisioning."
exit 1
