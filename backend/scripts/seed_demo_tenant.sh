#!/usr/bin/env bash
# Seed demo tenant with contacts, customers (accounts), and deals via API.
# Usage: ./scripts/seed_demo_tenant.sh [BASE_URL]
# Requires: curl, jq
# Credentials: DEMO_EMAIL (default demo@moio.ai), DEMO_PASS (default demo123)

set -e

BASE_URL="${1:-http://127.0.0.1:8093}"
DEMO_EMAIL="${DEMO_EMAIL:-demo@moio.ai}"
DEMO_PASS="${DEMO_PASS:-demo123}"
HOST="demo.127.0.0.1"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

_pass() { echo -e "${GREEN}[OK]${NC} $1"; }
_fail() { echo -e "${RED}[FAIL]${NC} $1"; exit 1; }
_step() { echo ""; echo "=== $1 ==="; }

# Login
_step "Login"
LOGIN_RESP=$(curl -sf -X POST "$BASE_URL/api/v1/auth/login/" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$DEMO_EMAIL\",\"password\":\"$DEMO_PASS\"}") || _fail "Login failed"
TOKEN=$(echo "$LOGIN_RESP" | jq -r '.access')
if [ -z "$TOKEN" ] || [ "$TOKEN" = "null" ]; then
  echo "$LOGIN_RESP" | jq .
  _fail "No access token"
fi
_pass "Logged in as $DEMO_EMAIL"

AUTH="Authorization: Bearer $TOKEN"
HDR="Host: $HOST"

# Ensure pipeline exists
_step "Pipeline (create-default)"
PIPE_RESP=$(curl -sf -X POST -H "$AUTH" -H "$HDR" -H "Content-Type: application/json" \
  "$BASE_URL/api/v1/crm/deals/pipelines/create-default/" 2>/dev/null) || true
if echo "$PIPE_RESP" | jq -e '.error' >/dev/null 2>&1; then
  # May already exist
  _pass "Pipeline check (may already exist)"
else
  _pass "Pipeline created"
fi

# Get pipeline and first stage for deals
_step "Get pipeline stages"
PIPES=$(curl -sf -H "$AUTH" -H "$HDR" "$BASE_URL/api/v1/crm/deals/pipelines/")
PIPELINE_ID=$(echo "$PIPES" | jq -r '.pipelines[0].id // .[0].id // empty')
STAGE_ID=$(echo "$PIPES" | jq -r '.pipelines[0].stages[0].id // .[0].stages[0].id // empty')
if [ -n "$PIPELINE_ID" ] && [ -n "$STAGE_ID" ]; then
  _pass "Pipeline: $PIPELINE_ID, Stage: $STAGE_ID"
else
  echo "$PIPES" | jq .
  PIPELINE_ID=""
  STAGE_ID=""
fi

# Create customers (accounts) - Business type, unique phone/email
_step "Creating customers (accounts)"
declare -a CUSTOMER_IDS

_customer() {
  local name="$1" legal="$2" email="$3" phone="$4"
  local resp
  resp=$(curl -sf -X POST -H "$AUTH" -H "$HDR" -H "Content-Type: application/json" \
    -d "{
      \"name\": \"$name\",
      \"legal_name\": \"$legal\",
      \"type\": \"Business\",
      \"email\": \"$email\",
      \"phone\": \"$phone\",
      \"status\": \"active\"
    }" \
    "$BASE_URL/api/v1/crm/customers/")
  if echo "$resp" | jq -e '.id' >/dev/null 2>&1; then
    echo "$resp" | jq -r '.id'
  else
    echo ""
  fi
}

CUSTOMER_IDS+=("$(_customer "Mercado Libre" "MercadoLibre, Inc." "contacto@mercadolibre.com" "+5491123456001")")
CUSTOMER_IDS+=("$(_customer "Google" "Google LLC" "enterprise@google.com" "+5491123456002")")
CUSTOMER_IDS+=("$(_customer "Microsoft" "Microsoft Corporation" "ventas@microsoft.com" "+5491123456003")")
CUSTOMER_IDS+=("$(_customer "Amazon" "Amazon.com, Inc." "b2b@amazon.com" "+5491123456004")")
CUSTOMER_IDS+=("$(_customer "Tesla" "Tesla, Inc." "fleet@tesla.com" "+5491123456005")")
CUSTOMER_IDS+=("$(_customer "Netflix" "Netflix, Inc." "partners@netflix.com" "+5491123456006")")
CUSTOMER_IDS+=("$(_customer "Globant" "Globant S.A." "hr@globant.com" "+5491123456007")")
CUSTOMER_IDS+=("$(_customer "dLocal" "dLocal Limited" "sales@dlocal.com" "+5491123456008")")

CREATED=0
for cid in "${CUSTOMER_IDS[@]}"; do
  [ -n "$cid" ] && CREATED=$((CREATED+1))
done
_pass "Customers created: $CREATED"

# Create contacts with full data
_step "Creating contacts"
declare -a CONTACT_IDS

_contact() {
  local fullname="$1" email="$2" phone="$3" company="$4" title="$5" first="$6" last="$7"
  local payload
  payload=$(jq -n \
    --arg fn "$fullname" \
    --arg em "$email" \
    --arg ph "$phone" \
    --arg co "$company" \
    --arg ti "$title" \
    --arg f "$first" \
    --arg l "$last" \
    '{
      name: $fn,
      fullname: $fn,
      first_name: $f,
      last_name: $l,
      email: $em,
      phone: $ph,
      company: $co,
      title: $ti,
      source: "seed"
    }')
  local resp
  resp=$(curl -sf -X POST -H "$AUTH" -H "$HDR" -H "Content-Type: application/json" \
    -d "$payload" \
    "$BASE_URL/api/v1/crm/contacts/")
  if echo "$resp" | jq -e '.id' >/dev/null 2>&1; then
    echo "$resp" | jq -r '.id'
  else
    echo ""
  fi
}

# Contacts linked to companies
CONTACT_IDS+=("$(_contact "Carlos Méndez" "carlos.mendez@mercadolibre.com" "+59899123401" "Mercado Libre" "Director Comercial" "Carlos" "Méndez")")
CONTACT_IDS+=("$(_contact "Ana Rodríguez" "ana.rodriguez@google.com" "+59899123402" "Google" "Account Executive" "Ana" "Rodríguez")")
CONTACT_IDS+=("$(_contact "Pedro Martínez" "pedro.martinez@microsoft.com" "+59899123403" "Microsoft" "Enterprise Sales" "Pedro" "Martínez")")
CONTACT_IDS+=("$(_contact "Laura Fernández" "laura.fernandez@amazon.com" "+59899123404" "Amazon" "Partner Manager" "Laura" "Fernández")")
CONTACT_IDS+=("$(_contact "Diego García" "diego.garcia@tesla.com" "+59899123405" "Tesla" "Fleet Sales" "Diego" "García")")
CONTACT_IDS+=("$(_contact "María López" "maria.lopez@netflix.com" "+59899123406" "Netflix" "Content Partnerships" "María" "López")")
CONTACT_IDS+=("$(_contact "Andrés Silva" "andres.silva@globant.com" "+59899123407" "Globant" "CTO" "Andrés" "Silva")")
CONTACT_IDS+=("$(_contact "Valentina Costa" "valentina.costa@dlocal.com" "+59899123408" "dLocal" "Head of Sales" "Valentina" "Costa")")
CONTACT_IDS+=("$(_contact "Roberto Pérez" "roberto.perez@acme.com" "+59899123409" "Acme Corp" "CEO" "Roberto" "Pérez")")
CONTACT_IDS+=("$(_contact "Lucía González" "lucia.gonzalez@startup.io" "+59899123410" "Startup.io" "Co-Founder" "Lucía" "González")")

CREATED=0
for cid in "${CONTACT_IDS[@]}"; do
  [ -n "$cid" ] && CREATED=$((CREATED+1))
done
_pass "Contacts created: $CREATED"

# Create deals
_step "Creating deals"
DEAL_COUNT=0

_deal() {
  local title="$1" value="$2" contact_id="$3" priority="$4"
  local payload
  if [ -n "$contact_id" ] && [ -n "$PIPELINE_ID" ] && [ -n "$STAGE_ID" ]; then
    payload=$(jq -n \
      --arg t "$title" \
      --argjson v "$value" \
      --arg c "$contact_id" \
      --arg p "$PIPELINE_ID" \
      --arg s "$STAGE_ID" \
      --arg pr "${priority:-medium}" \
      '{
        title: $t,
        description: "Deal creado por seed",
        value: $v,
        currency: "USD",
        contact: $c,
        pipeline: $p,
        stage: $s,
        priority: $pr
      }')
  else
    payload=$(jq -n \
      --arg t "$title" \
      --argjson v "$value" \
      --arg pr "${priority:-medium}" \
      '{
        title: $t,
        description: "Deal creado por seed",
        value: $v,
        currency: "USD",
        priority: $pr
      }')
  fi
  local resp
  resp=$(curl -sf -X POST -H "$AUTH" -H "$HDR" -H "Content-Type: application/json" \
    -d "$payload" \
    "$BASE_URL/api/v1/crm/deals/")
  if echo "$resp" | jq -e '.id' >/dev/null 2>&1; then
    DEAL_COUNT=$((DEAL_COUNT+1))
  fi
}

# Deals with contacts (use first few contact IDs)
C0="${CONTACT_IDS[0]}"
C1="${CONTACT_IDS[1]}"
C2="${CONTACT_IDS[2]}"
C3="${CONTACT_IDS[3]}"
C4="${CONTACT_IDS[4]}"
C5="${CONTACT_IDS[5]}"

_deal "Licencias Enterprise - Mercado Libre" 85000 "$C0" "high"
_deal "Contrato Google Workspace" 24000 "$C1" "medium"
_deal "Microsoft 365 - 500 usuarios" 42000 "$C2" "high"
_deal "AWS - Migración cloud" 125000 "$C3" "urgent"
_deal "Flota Tesla - 10 vehículos" 450000 "$C4" "high"
_deal "Partnership contenido Netflix" 35000 "$C5" "medium"
_deal "Proyecto desarrollo Globant" 180000 "${CONTACT_IDS[6]}" "high"
_deal "Integración pagos dLocal" 28000 "${CONTACT_IDS[7]}" "medium"
_deal "Consultoría estratégica Acme" 15000 "${CONTACT_IDS[8]}" "low"
_deal "SaaS Startup.io - seed" 12000 "${CONTACT_IDS[9]}" "medium"

# Some deals without contact (if pipeline exists)
_deal "Lead inbound - pendiente asignar" 8000 "" "low"
_deal "Oportunidad web" 5500 "" "medium"

_pass "Deals created: $DEAL_COUNT"

_step "Done"
echo "Demo tenant seeded: customers, contacts, deals."
echo "List: curl -s -H \"$AUTH\" -H \"$HDR\" \"$BASE_URL/api/v1/crm/contacts/?limit=5\" | jq"
echo "      curl -s -H \"$AUTH\" -H \"$HDR\" \"$BASE_URL/api/v1/crm/customers/?limit=5\" | jq"
echo "      curl -s -H \"$AUTH\" -H \"$HDR\" \"$BASE_URL/api/v1/crm/deals/\" | jq"
