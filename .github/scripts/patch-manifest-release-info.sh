#!/usr/bin/env bash
# Set ota.summary on ESP-Web-Tools manifests from GitHub Release metadata.
# Usage: RELEASE_TAG=... RELEASE_NAME=... RELEASE_BODY=... patch-manifest-release-info.sh <dir>
set -euo pipefail

ROOT="${1:?directory required}"
RELEASE_TAG="${RELEASE_TAG:?RELEASE_TAG required}"
RELEASE_NAME="${RELEASE_NAME:-}"
RELEASE_BODY="${RELEASE_BODY:-}"

while IFS= read -r -d '' m; do
  tmp=$(mktemp)
  jq --arg tag "$RELEASE_TAG" \
    --arg name "$RELEASE_NAME" \
    --arg body "$RELEASE_BODY" \
    '
      (if ($name != "" and $name != $tag) then "\($tag) — \($name)" else $tag end) as $header
      | (if ($body != "") then $header + "\n\n" + $body else $header end) as $summary
      | if .builds then
          .builds |= map(if .ota then .ota.summary = $summary else . end)
        else .
        end
    ' "$m" > "$tmp"
  mv "$tmp" "$m"
  echo "release summary: $m"
done < <(find "$ROOT" -type f \( -name 'manifest.json' -o -name '*.manifest.json' \) -print0)
