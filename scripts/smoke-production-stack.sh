#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 || -z "${1:-}" ]]; then
  printf 'Usage: %s BASE_URL\n' "$0" >&2
  exit 2
fi

BASE_URL=${1%/}
WORK_DIR=$(mktemp -d)
COOKIE_JAR="$WORK_DIR/cookies.txt"
HEADERS="$WORK_DIR/headers.txt"
BODY="$WORK_DIR/body.txt"
trap 'rm -rf "$WORK_DIR"' EXIT

stage() {
  printf '\n==> %s\n' "$1"
}

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  exit 1
}

request() {
  local method=$1
  local path=$2
  shift 2
  curl --silent --show-error --location \
    --request "$method" \
    --dump-header "$HEADERS" \
    --output "$BODY" \
    --write-out '%{http_code}' \
    "$@" \
    "$BASE_URL$path"
}

media_type() {
  awk 'BEGIN { IGNORECASE=1 } /^content-type:/ { value=$0 } END { sub(/^[^:]*:[[:space:]]*/, "", value); sub(/;.*/, "", value); sub(/\r$/, "", value); print tolower(value) }' "$HEADERS"
}

expect_response() {
  local expected_status=$1
  local expected_type=$2
  local actual_status=$3
  local actual_type
  actual_type=$(media_type)
  [[ "$actual_status" == "$expected_status" ]] || fail "expected HTTP $expected_status, got $actual_status"
  [[ "$actual_type" == "$expected_type" ]] || fail "expected media type $expected_type, got ${actual_type:-<missing>}"
}

expect_body() {
  grep -Fq -- "$1" "$BODY" || fail "response body did not contain expected marker: $1"
}

stage "health"
status=$(request GET /health)
expect_response 200 application/json "$status"
expect_body '"status":"ok"'

stage "readiness"
status=$(request GET /api/v1/ready)
expect_response 200 application/json "$status"
expect_body '"status":"ready"'

stage "public frontend"
status=$(request GET /)
expect_response 200 text/html "$status"
expect_body '<div id="root"></div>'

stage "crawler contracts"
status=$(request GET /robots.txt)
expect_response 200 text/plain "$status"
expect_body 'User-agent: *'
expect_body "Sitemap: $BASE_URL/sitemap.xml"
status=$(request GET /sitemap.xml)
expect_response 200 application/xml "$status"
expect_body '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
expect_body "<loc>$BASE_URL/</loc>"

stage "anonymous session rejection"
status=$(request GET /api/v1/auth/session)
expect_response 401 application/problem+json "$status"
expect_body '"code":"authentication_required"'

stage "signup and protected session"
unique="$(date +%s)-$$"
email="production-smoke-${unique}@example.com"
password="Release-${unique}-Aa1!"
signup_payload=$(printf '{"email":"%s","password":"%s","confirm_password":"%s","turnstile_token":""}' "$email" "$password" "$password")
status=$(request POST /api/v1/auth/signup \
  --header 'Content-Type: application/json' \
  --cookie-jar "$COOKIE_JAR" \
  --data "$signup_payload")
expect_response 200 application/json "$status"
expect_body '"status":"authenticated"'
csrf_token=$(sed -n 's/.*"csrf_token":"\([^"]*\)".*/\1/p' "$BODY")
[[ -n "$csrf_token" ]] || fail "signup response did not contain a CSRF token"

status=$(request GET /api/v1/auth/session --cookie "$COOKIE_JAR" --cookie-jar "$COOKIE_JAR")
expect_response 200 application/json "$status"
expect_body "\"email\":\"$email\""

access_cookie=$(awk '$0 !~ /^#/ && $6 ~ /rentivo_access$/ { value=$6 "=" $7 } END { print value }' "$COOKIE_JAR")
if [[ -z "$access_cookie" ]]; then
  access_cookie=$(awk '$0 ~ /^#HttpOnly_/ && $6 ~ /rentivo_access$/ { value=$6 "=" $7 } END { print value }' "$COOKIE_JAR")
fi
[[ -n "$access_cookie" ]] || fail "signup did not issue a login-token cookie"

stage "logout and server-side token revocation"
status=$(request POST /api/v1/auth/logout \
  --header "X-CSRF-Token: $csrf_token" \
  --cookie "$COOKIE_JAR" \
  --cookie-jar "$COOKIE_JAR")
[[ "$status" == "204" ]] || fail "expected HTTP 204 from logout, got $status"
[[ ! -s "$BODY" ]] || fail "expected an empty logout response body"

status=$(request GET /api/v1/auth/session --header "Cookie: $access_cookie")
expect_response 401 application/problem+json "$status"
expect_body '"code":"authentication_required"'

stage "password login after logout"
login_payload=$(printf '{"email":"%s","password":"%s","turnstile_token":""}' "$email" "$password")
status=$(request POST /api/v1/auth/login \
  --header 'Content-Type: application/json' \
  --cookie-jar "$COOKIE_JAR" \
  --data "$login_payload")
expect_response 200 application/json "$status"
expect_body '"status":"authenticated"'

printf '\nProduction stack smoke checks passed.\n'
