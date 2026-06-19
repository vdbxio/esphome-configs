#!/usr/bin/env bash
# Patch manifest name (friendly_name) and ota.summary (release metadata).
set -euo pipefail

ROOT="${1:?directory required}"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
RELEASE_TAG="${RELEASE_TAG:?RELEASE_TAG required}"
RELEASE_NAME="${RELEASE_NAME:-}"
RELEASE_BODY="${RELEASE_BODY:-}"

friendly_name_for() {
  local device="$1" yaml line
  for yaml in "${device}.yaml" "${device}.factory.yaml"; do
    [ -f "${REPO_ROOT}/${yaml}" ] || continue
    line=$(grep -E '^[[:space:]]*friendly_name:' "${REPO_ROOT}/${yaml}" | head -1) || continue
    echo "$line" | sed -E 's/.*friendly_name:[[:space:]]*"?([^"#]+)"?.*/\1/' | sed 's/[[:space:]]*$//'
    return 0
  done
  return 1
}

while IFS= read -r -d '' m; do
  device=$(basename "$m" .manifest.json)
  [ "$device" = "manifest" ] && continue
  friendly=$(friendly_name_for "$device" || true)
  tmp=$(mktemp)
  jq --arg tag "$RELEASE_TAG" \
    --arg name "$RELEASE_NAME" \
    --arg body "$RELEASE_BODY" \
    --arg friendly "$friendly" \
    '
      (if ($name != "" and $name != $tag) then "\($tag) — \($name)" else $tag end) as $header
      | (if ($body != "") then $header + "\n\n" + $body else $header end) as $summary
      | (if $friendly != "" then .name = $friendly else . end)
      | if .builds then
          .builds |= map(if .ota then .ota.summary = $summary else . end)
        else .
        end
    ' "$m" > "$tmp"
  mv "$tmp" "$m"
  echo "patched: $m (name=${friendly:-unchanged})"
done < <(find "$ROOT" -type f \( -name 'manifest.json' -o -name '*.manifest.json' \) -print0)
