#!/usr/bin/env bash
# scripts/tag_history.sh
#
# One-shot retroactive tagger. Idempotent: skips any tag/release that already exists.
#
# Pre-flight:
#   - gh CLI authenticated (`gh auth status`)
#   - run from repo root
#   - `main` is checked out and up to date
#   - CHANGELOG.md has an entry for every version below
#
# Usage:
#   scripts/tag_history.sh                # tag + push + create releases
#   scripts/tag_history.sh --dry-run      # print actions only
#   scripts/tag_history.sh --tags-only    # local tags, no push, no releases

set -euo pipefail

DRY_RUN=0
TAGS_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --dry-run)  DRY_RUN=1 ;;
    --tags-only) TAGS_ONLY=1 ;;
    *) echo "unknown arg: $arg" >&2; exit 2 ;;
  esac
done

# version<TAB>sha — keep in sync with CHANGELOG.md and the plan's mapping table
MAPPING=$(cat <<'EOF'
0.1.0	7d5b9f0
0.2.0	a484e85
0.3.0	6cf80ee
0.4.0	2ee9888
0.5.0	e39f51e
1.0.0	8e43705
1.1.0	07624e7
1.2.0	359c337
1.3.0	d9f869c
1.4.0	3c2b2ba
1.5.0	ff169c1
1.6.0	16e5ea5
1.7.0	b521288
1.8.0	638ffe2
1.9.0	8410e9a
2.0.0	281ab3e
2.1.0	870ca48
2.2.0	eb1be9b
2.3.0	43e2659
2.4.0	02f14c5
2.5.0	702241f
2.6.0	2a46e19
2.7.0	e9ab2d8
2.8.0	cb51533
2.9.0	521904c
2.10.0	6a178eb
2.11.0	71b6be5
2.12.0	f490dbb
3.0.0	24fffc1
3.1.0	77cb58b
3.2.0	ad5ca9f
3.3.0	c402b1c
3.4.0	950858f
3.5.0	a3b5853
3.6.0	091cd4a
3.6.1	b4b9f3f
3.6.2	b56e664
3.7.0	596654d
3.7.1	f8ef8ad
3.8.0	7b37b0a
3.9.0	d8e3ded
EOF
)

run() {
  if [ "$DRY_RUN" = "1" ]; then
    echo "DRY: $*"
  else
    eval "$@"
  fi
}

extract_notes() {
  # $1 = version (no leading v)
  awk -v ver="$1" '
    BEGIN { found = 0 }
    /^## \[/ {
      if (found) exit
      if (index($0, "[" ver "]") > 0) { found = 1; next }
    }
    /^\[.*\]: / {
      if (found) exit
    }
    found { print }
  ' CHANGELOG.md
}

# Step 1: create all local tags (skip existing).
while IFS=$'\t' read -r version sha; do
  [ -z "$version" ] && continue
  tag="v$version"
  if git rev-parse -q --verify "refs/tags/$tag" >/dev/null; then
    echo "tag exists, skip: $tag"
    continue
  fi
  if ! git cat-file -e "$sha^{commit}" 2>/dev/null; then
    echo "::error:: sha $sha (for $tag) not in history — aborting" >&2
    exit 1
  fi
  run git tag -a "$tag" "$sha" -m "Release $tag"
done <<< "$MAPPING"

# Step 2: push tags.
if [ "$TAGS_ONLY" = "1" ]; then
  echo "--tags-only: stopping before push + release creation"
  exit 0
fi
run git push origin --tags

# Step 3: create one GitHub Release per tag, with notes from CHANGELOG.md.
while IFS=$'\t' read -r version sha; do
  [ -z "$version" ] && continue
  tag="v$version"
  if gh release view "$tag" >/dev/null 2>&1; then
    echo "release exists, skip: $tag"
    continue
  fi
  notes=$(extract_notes "$version")
  if [ -z "$notes" ]; then
    echo "::error:: CHANGELOG.md has no entry for $version — aborting" >&2
    exit 1
  fi
  tmp=$(mktemp)
  printf '%s\n' "$notes" > "$tmp"
  run gh release create "$tag" --title "Release $tag" --notes-file "$tmp"
  rm -f "$tmp"
done <<< "$MAPPING"

echo "Done. Created tags + releases for $(echo "$MAPPING" | wc -l | tr -d ' ') versions."
