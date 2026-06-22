# GitHub Actions

CI and release automation for ESPHome configs in this repo.

## Overview

```
PR / nightly          →  CI (compile smoke test)
GitHub Release        →  Publish Firmware (build + upload assets)
                      →  Publish Pages (deploy site + firmware manifests)
weekly                →  Dependabot (action version bumps)
```

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| [CI](workflows/ci.yml) | PR (yaml changes), nightly | Compile-only validation |
| [Publish Firmware](workflows/publish-firmware.yml) | Release published | Build bins + manifests, attach to release |
| [Publish Pages](workflows/publish-pages.yml) | After Publish Firmware, PR on `static/` | Deploy GitHub Pages site |
| [Dependabot](dependabot.yml) | Weekly | Bump GitHub Actions versions |

---

## CI

**File:** `workflows/ci.yml`

Validates that configs compile. Does not flash hardware or publish firmware.

**When it runs**
- Pull requests that touch `*.yaml` or this workflow
- Daily at midnight UTC (catches breakage from ESPHome `latest`)

**Matrix builds**
- `flip-c3.factory.yaml` — factory firmware (web installer)
- `flip-c3.import.yaml` — dashboard adopt template
- `pwrtool500.factory.yaml` — factory firmware (managed OTA)
- `pwrtool500.import.yaml` — dashboard adopt template

`flip-c3.yaml` is kept for legacy dashboard references only — not built in CI or releases.

Each yaml is compiled against ESPHome `latest`. Import yamls need WiFi secrets; CI writes a stub `secrets.yaml`.

---

## Publish Firmware

**File:** `workflows/publish-firmware.yml`

Runs when a **published** GitHub Release is created (drafts do not trigger).

### Job: Build Firmware

Uses [esphome/workflows build.yml](https://github.com/esphome/workflows) to compile:

- `flip-c3.factory.yaml` — web installer manifest + bins (no device OTA)
- `pwrtool500.factory.yaml` — factory firmware with managed OTA

Before compile, `version: dev` in yaml is replaced with the release tag (e.g. `0.9.5`).

ESPHome version is pinned in the workflow (`esphome-version: 2026.6.0`).

### Job: Upload to Release

1. Downloads build artifacts (one folder per product: `flip-c3/`, `pwrtool500/`)
2. Packages flat release assets: `*.bin`, `*.manifest.json`, `.md5`, `.sha256`
3. Runs helper scripts (see below)
4. Uploads to the GitHub Release with `gh release upload --clobber`

**Release assets look like:**
```
flip-c3.factory.bin
flip-c3.ota.bin
flip-c3.manifest.json
pwrtool500.factory.bin
pwrtool500.ota.bin
pwrtool500.manifest.json
```

---

## Publish Pages

**File:** `workflows/publish-pages.yml`

Deploys the static site and **latest release firmware** to GitHub Pages.

**When it runs**
- Automatically after **Publish Firmware** completes (success or failure — check logs if Pages looks stale)
- PRs that change `static/` or this workflow (build only; publish job is skipped)

**What it does**
1. Builds `static/` with Jekyll
2. Downloads all assets from the newest published release
3. Lays out firmware per product under `firmware/{product}/`
4. Deploys to the `github-pages` environment

**Stable manifest URLs** (same path every release, content overwritten):

- https://vdbxio.github.io/esphome-configs/firmware/pwrtool500/manifest.json
- https://vdbxio.github.io/esphome-configs/firmware/flip-c3/manifest.json

PwrTool factory devices fetch OTA from the pwrtool500 URL via `packages/vdbx-managed-ota.yaml`.

---

## Helper scripts

### `scripts/normalize-firmware-names.sh`

ESPHome 2026.6+ embeds the chip in filenames (e.g. `pwrtool500-esp32c3.ota.bin`). This script:

- Renames `*-esp32c3*` files to drop the chip suffix
- Updates `ota.path` and `parts[].path` in manifests to match

Used in both Publish Firmware and Publish Pages.

### `scripts/patch-manifest-release-info.sh`

Runs after normalize, before release upload. Patches each `*.manifest.json`:

| Field | Source |
|-------|--------|
| `name` | `friendly_name` from product yaml |
| `builds[].ota.summary` | Release tag, title, and description |
| `builds[].ota.release_url` | Set at build time from release URL |

Release notes are patched here (not passed to build-action) because multiline release bodies break the action’s shell heredoc.

---

## Cutting a release

1. Merge changes to `main`
2. Create a GitHub Release with a semver tag (e.g. `0.9.6`)
3. Add a title and description (description becomes manifest summary)
4. **Publish Firmware** runs → assets on the release
5. **Publish Pages** runs → live manifest URLs update

Re-running a failed workflow uses the **original commit’s workflow file**. To pick up workflow fixes, publish a new release tag.

---

## Dependabot

**File:** `dependabot.yml`

Weekly PRs to bump GitHub Actions dependency versions (`package-ecosystem: github-actions`).
