#!/usr/bin/env bash
# Run the API startup testing protocol for test and/or test_2 tenants.
# Usage:
#   ./scripts/run_api_startup_protocol.sh [test|test_2|all] [BASE_URL]
# Example:
#   ./scripts/run_api_startup_protocol.sh test
#   ./scripts/run_api_startup_protocol.sh all http://127.0.0.1:8093
#
# Credentials: configure TEST_EMAIL/TEST_PASS for test, TEST2_EMAIL/TEST2_PASS for test_2.
# Default test:  test@moio.ai / test123
# Default test_2: test2@moio.ai / test123

set -e

TENANT="${1:-test}"
BASE_URL="${2:-http://127.0.0.1:8093}"

# Credentials (override via env)
TEST_EMAIL="${TEST_EMAIL:-test@moio.ai}"
TEST_PASS="${TEST_PASS:-test123}"
TEST2_EMAIL="${TEST2_EMAIL:-test2@moio.ai}"
TEST2_PASS="${TEST2_PASS:-test123}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

_pass() { echo -e "${GREEN}[OK]${NC} $1"; }
_fail() { echo -e "${RED}[FAIL]${NC} $1"; exit 1; }
_skip() { echo -e "${YELLOW}[SKIP]${NC} $1"; }
_step() { echo ""; echo "=== $1 ==="; }

run_tenant() {
  local subdomain="$1"
  local email="$2"
  local pass="$3"
  # Use host without underscore (RFC: test_2 -> test2) for API requests
  local host
  host=$(echo "$subdomain" | tr '_' ' ')
  host="${host// /}.127.0.0.1"

  _step "Tenant: $subdomain (Host: $host)"

  # 1. Health
  _step "1.1 Health check"
  if curl -sf "$BASE_URL/api/v1/health/" > /dev/null; then
    _pass "Health OK"
  else
    _fail "Health check failed"
  fi

  # 2. Login
  _step "1.2 Login"
  local login_resp
  login_resp=$(curl -sf -X POST "$BASE_URL/api/v1/auth/login/" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$email\",\"password\":\"$pass\"}") || _fail "Login failed"
  TOKEN=$(echo "$login_resp" | jq -r '.access')
  if [ -z "$TOKEN" ] || [ "$TOKEN" = "null" ]; then
    echo "$login_resp" | jq .
    _fail "No access token in login response"
  fi
  _pass "Login OK (token length: ${#TOKEN})"

  # 3. Bootstrap
  _step "1.3 Bootstrap"
  local boot
  boot=$(curl -sf -H "Authorization: Bearer $TOKEN" -H "Host: $host" "$BASE_URL/api/v1/bootstrap/") || _fail "Bootstrap failed"
  local boot_user=$(echo "$boot" | jq -r '.user.email // empty')
  local boot_tenant=$(echo "$boot" | jq -r '.tenant.nombre // empty')
  if [ -n "$boot_user" ] && [ -n "$boot_tenant" ]; then
    _pass "Bootstrap OK (user=$boot_user, tenant=$boot_tenant)"
  else
    echo "$boot" | jq .
    _fail "Bootstrap response incomplete"
  fi

  # 4. Create users (member, manager)
  _step "1.4 Create users"
  local member_email="member@${subdomain}.moio.ai"
  local manager_email="manager@${subdomain}.moio.ai"
  if curl -sf -X POST -H "Authorization: Bearer $TOKEN" -H "Host: $host" -H "Content-Type: application/json" \
    -d "{\"email\":\"$member_email\",\"username\":\"$member_email\",\"first_name\":\"Member\",\"last_name\":\"User\",\"password\":\"member123\",\"role\":\"member\"}" \
    "$BASE_URL/api/v1/users/" | jq -e '.id' > /dev/null 2>&1; then
    _pass "Created member user"
  else
    _skip "Member user may already exist"
  fi
  if curl -sf -X POST -H "Authorization: Bearer $TOKEN" -H "Host: $host" -H "Content-Type: application/json" \
    -d "{\"email\":\"$manager_email\",\"username\":\"$manager_email\",\"first_name\":\"Manager\",\"last_name\":\"User\",\"password\":\"manager123\",\"role\":\"manager\"}" \
    "$BASE_URL/api/v1/users/" | jq -e '.id' > /dev/null 2>&1; then
    _pass "Created manager user"
  else
    _skip "Manager user may already exist"
  fi

  # 5. Create contacts (use unique suffix for repeated runs)
  _step "1.5 Create contacts"
  local suffix
  suffix=$(date +%s 2>/dev/null || echo "$$")
  local c1 c2
  c1=$(curl -sf -X POST -H "Authorization: Bearer $TOKEN" -H "Host: $host" -H "Content-Type: application/json" \
    -d "{\"fullname\":\"Juan Pérez ($subdomain)\",\"email\":\"juan${suffix}@${subdomain}.example.com\",\"phone\":\"+59899123${suffix: -4}\",\"company\":\"Acme SA\"}" \
    "$BASE_URL/api/v1/crm/contacts/") || _fail "Create contact 1 failed"
  CONTACT_ID=$(echo "$c1" | jq -r '.id // empty')
  if [ -n "$CONTACT_ID" ]; then
    _pass "Contact 1 created (id=$CONTACT_ID)"
  else
    echo "$c1" | jq .
    _fail "Contact 1 response missing id"
  fi
  c2=$(curl -sf -X POST -H "Authorization: Bearer $TOKEN" -H "Host: $host" -H "Content-Type: application/json" \
    -d "{\"fullname\":\"María García ($subdomain)\",\"email\":\"maria${suffix}@${subdomain}.example.com\",\"phone\":\"+59898765${suffix: -4}\"}" \
    "$BASE_URL/api/v1/crm/contacts/") || _fail "Create contact 2 failed"
  _pass "Contact 2 created"

  # 6. Create customer
  _step "1.6 Create customer"
  local cust
  cust=$(curl -sf -X POST -H "Authorization: Bearer $TOKEN" -H "Host: $host" -H "Content-Type: application/json" \
    -d "{\"name\":\"Acme Corp ($subdomain)\",\"legal_name\":\"Acme Corporation SA\",\"type\":\"company\",\"email\":\"info${suffix}@${subdomain}-acme.com\",\"phone\":\"+59829${suffix: -6}\"}" \
    "$BASE_URL/api/v1/crm/customers/") || _fail "Create customer failed"
  _pass "Customer created"

  # 7. Create default pipeline (ignore 400 if already exists)
  _step "1.7 Create default pipeline"
  local pipe_resp
  pipe_resp=$(curl -sf -X POST -H "Authorization: Bearer $TOKEN" -H "Host: $host" "$BASE_URL/api/v1/crm/deals/pipelines/create-default/" 2>/dev/null) || true
  if echo "$pipe_resp" | jq -e '.id' > /dev/null 2>&1; then
    PIPELINE_ID=$(echo "$pipe_resp" | jq -r '.id')
    STAGE_ID=$(echo "$pipe_resp" | jq -r '.stages[0].id // empty')
    _pass "Pipeline created (id=$PIPELINE_ID)"
  elif echo "$pipe_resp" 2>/dev/null | grep -q "already exist"; then
    # Fetch existing pipeline
    pipe_list=$(curl -sf -H "Authorization: Bearer $TOKEN" -H "Host: $host" "$BASE_URL/api/v1/crm/deals/pipelines/")
    PIPELINE_ID=$(echo "$pipe_list" | jq -r '.pipelines[0].id // empty')
    STAGE_ID=$(echo "$pipe_list" | jq -r '.pipelines[0].stages[0].id // empty')
    _skip "Pipeline already exists"
  else
    PIPELINE_ID=""
    STAGE_ID=""
    _skip "Could not get pipeline (deals may work without)"
  fi

  # 8. Create deal
  _step "1.8 Create deal"
  local deal_payload="{\"title\":\"Deal Acme - Licencias ($subdomain)\",\"description\":\"Venta de 50 licencias\",\"value\":5000,\"currency\":\"USD\"}"
  if [ -n "$CONTACT_ID" ] && [ "$CONTACT_ID" != "null" ]; then
    deal_payload=$(echo "$deal_payload" | jq --arg c "$CONTACT_ID" '. + {contact: $c}')
  fi
  if [ -n "$PIPELINE_ID" ] && [ "$PIPELINE_ID" != "null" ] && [ -n "$STAGE_ID" ] && [ "$STAGE_ID" != "null" ]; then
    deal_payload=$(echo "$deal_payload" | jq --arg p "$PIPELINE_ID" --arg s "$STAGE_ID" '. + {pipeline: $p, stage: $s}')
  fi
  local deal_resp
  deal_resp=$(curl -sf -X POST -H "Authorization: Bearer $TOKEN" -H "Host: $host" -H "Content-Type: application/json" \
    -d "$deal_payload" "$BASE_URL/api/v1/crm/deals/") || _fail "Create deal failed"
  DEAL_ID=$(echo "$deal_resp" | jq -r '.id // empty')
  _pass "Deal created (id=$DEAL_ID)"

  # 9. Create activity
  _step "1.9 Create activity"
  local act_payload="{\"title\":\"Llamada de seguimiento ($subdomain)\",\"kind\":\"note\",\"content\":{\"body\":\"Cliente interesado\"},\"status\":\"completed\",\"visibility\":\"public\"}"
  if [ -n "$CONTACT_ID" ] && [ "$CONTACT_ID" != "null" ]; then
    act_payload=$(echo "$act_payload" | jq --arg c "$CONTACT_ID" '. + {contact_id: $c}')
  fi
  local act_resp
  act_resp=$(curl -sf -X POST -H "Authorization: Bearer $TOKEN" -H "Host: $host" -H "Content-Type: application/json" \
    -d "$act_payload" "$BASE_URL/api/v1/activities/") || _fail "Create activity failed"
  _pass "Activity created"

  echo ""
  _pass "Protocol completed for tenant $subdomain"
}

# Main
echo "API Startup Protocol — Base: $BASE_URL"
echo "Tenant(s): $TENANT"
echo ""

case "$TENANT" in
  test)
    run_tenant "test" "$TEST_EMAIL" "$TEST_PASS"
    ;;
  test_2|test2)
    run_tenant "test_2" "$TEST2_EMAIL" "$TEST2_PASS"
    ;;
  all)
    run_tenant "test" "$TEST_EMAIL" "$TEST_PASS"
    run_tenant "test_2" "$TEST2_EMAIL" "$TEST2_PASS"
    ;;
  *)
    echo "Usage: $0 [test|test_2|all] [BASE_URL]"
    exit 1
    ;;
esac

echo ""
echo "Protocol finished successfully."
