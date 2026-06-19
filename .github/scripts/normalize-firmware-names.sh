#!/usr/bin/env bash
# Strip -esp32c3 from ESPHome 2026.6+ firmware asset names and fix manifest paths.
# Usage: normalize-firmware-names.sh <directory>
set -euo pipefail

ROOT="${1:?directory required}"

# pwrtool500-esp32c3.ota.bin → pwrtool500.ota.bin (and .md5 / .sha256 sidecars)
while IFS= read -r -d '' f; do
  base=$(basename "$f")
  dir=$(dirname "$f")
  new="${base//-esp32c3/}"
  [ "$base" = "$new" ] && continue
  mv "$f" "$dir/$new"
  echo "renamed: $base → $new"
done < <(find "$ROOT" -type f -name '*-esp32c3*' -print0)

# manifest ota.path / parts[].path must match renamed binaries
while IFS= read -r -d '' m; do
  tmp=$(mktemp)
  jq '
    if .builds then
      .builds |= map(
        (if .ota and .ota.path then .ota.path |= gsub("-esp32c3"; "") else . end)
        | (if .parts then .parts |= map(
            if .path then .path |= gsub("-esp32c3"; "") else . end
          ) else . end)
      )
    else .
    end
  ' "$m" > "$tmp"
  mv "$tmp" "$m"
  echo "patched manifest: $m"
done < <(find "$ROOT" -type f \( -name 'manifest.json' -o -name '*.manifest.json' \) -print0)
