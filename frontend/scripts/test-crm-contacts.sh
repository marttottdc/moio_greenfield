#!/usr/bin/env bash
# Test GET /api/v1/crm/contacts/ using Bearer (JWT) token.
# Usage:
#   ./scripts/test-crm-contacts.sh                    # use BASE_URL and credentials from env
#   BASE_URL=https://devcrm.moio.ai/api/v1 ./scripts/test-crm-contacts.sh
#
# Env (optional):
#   BASE_URL   - API base (e.g. https://devcrm.moio.ai/api/v1 or http://localhost:5005/api/v1). No trailing slash.
#   API_USER   - login username or email
#   API_PASS   - login password
#   ACCESS_TOKEN - if set, skip login and use this JWT (overrides API_USER/API_PASS)

set -e
BASE_URL="${BASE_URL:-http://localhost:5005/api/v1}"
BASE_URL="${BASE_URL%/}"

if [[ -n "$ACCESS_TOKEN" ]]; then
  echo "Using ACCESS_TOKEN from env (Bearer auth)."
  TOKEN="$ACCESS_TOKEN"
else
  if [[ -z "$API_USER" || -z "$API_PASS" ]]; then
    echo "Set API_USER and API_PASS (or ACCESS_TOKEN) to test. Example:"
    echo "  API_USER=you@example.com API_PASS=secret $0"
    echo "  ACCESS_TOKEN=eyJ... $0"
    exit 1
  fi
  echo "Logging in to $BASE_URL ..."
  RESP=$(curl -s -X POST "$BASE_URL/auth/login/" \
    -H "Content-Type: application/json" \
    -d "{\"username\":\"$API_USER\",\"password\":\"$API_PASS\"}")
  TOKEN=$(echo "$RESP" | jq -r '.access // empty')
  if [[ -z "$TOKEN" ]]; then
    echo "Login failed. Response:"
    echo "$RESP" | jq . 2>/dev/null || echo "$RESP"
    exit 1
  fi
  echo "Login OK, got access token."
fi

echo "GET $BASE_URL/crm/contacts/"
curl -s -w "\nHTTP %{http_code}\n" -X GET "$BASE_URL/crm/contacts/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" | tee /tmp/crm-contacts-response.txt
