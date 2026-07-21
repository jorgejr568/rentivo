#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
source_contract="$repo_root/frontend/openapi.json"
ios_contract="$repo_root/ios/Rentivo/openapi.json"

case "${1:-sync}" in
  sync)
    cp "$source_contract" "$ios_contract"
    ;;
  check)
    if ! cmp -s "$source_contract" "$ios_contract"; then
      echo "ios/Rentivo/openapi.json is stale; run make ios-openapi-sync" >&2
      exit 1
    fi
    ;;
  *)
    echo "usage: $0 [sync|check]" >&2
    exit 64
    ;;
esac
