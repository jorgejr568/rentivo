#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

export RENTIVO_SMOKE_LIB_ONLY=1
# shellcheck source=../smoke-production-stack.sh
source "$ROOT_DIR/scripts/smoke-production-stack.sh"

assert_media_type() {
  local expected=$1
  local fixture=$2
  HEADERS="$WORK_DIR/headers.txt"
  printf '%s' "$fixture" > "$HEADERS"
  local actual
  actual=$(media_type)
  if [[ "$actual" != "$expected" ]]; then
    printf 'expected %s, got %s\n' "$expected" "${actual:-<missing>}" >&2
    exit 1
  fi
}

assert_media_type application/json $'HTTP/1.1 200 OK\r\nContent-Type: application/json; charset=utf-8\r\n\r\n'
assert_media_type text/plain $'HTTP/1.1 200 OK\r\ncontent-type: text/plain\r\n\r\n'
assert_media_type application/xml $'HTTP/1.1 200 OK\r\nCoNtEnT-TyPe: application/xml; charset=utf-8\r\n\r\n'
assert_media_type application/problem+json $'HTTP/1.1 302 Found\r\nContent-Type: text/html\r\nLocation: /final\r\n\r\nHTTP/1.1 401 Unauthorized\r\ncontent-type: application/problem+json; charset=utf-8\r\n\r\n'

printf 'smoke production stack shell tests passed\n'
