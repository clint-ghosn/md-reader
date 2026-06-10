# Phase 3: Release Automation Codex Runbook

**Codex goal:** Automate tagged releases so GitHub produces downloadable MD Reader installer, portable ZIP, checksums, and release notes.

**Phase output:** A GitHub Actions release workflow and supporting release-note script or template.

**Repo root:** `D:\Dev\workspace\md-reader`

**Prerequisites:** Phase 1 build hardening and Phase 2 installer support are complete.

## Technical References

- GitHub Actions workflow syntax and `permissions` control `GITHUB_TOKEN` access. Official docs: https://docs.github.com/en/actions/writing-workflows/workflow-syntax-for-github-actions
- GitHub-hosted runners support `windows-latest`. Official docs: https://docs.github.com/en/actions/how-tos/using-github-hosted-runners/using-github-hosted-runners
- GitHub CLI `gh release create` can create a release and upload asset files. Official docs: https://cli.github.com/manual/gh_release_create
- GitHub REST release assets are available if `gh` is not suitable. Official docs: https://docs.github.com/en/rest/releases/assets

## Execution Rules For Codex

1. Keep existing `.github\workflows\ci.yml` for push and pull-request validation.
2. Add a separate release workflow for tags.
3. Do not publish releases on every push to `main`.
4. Use `contents: write` only in the release job that creates the GitHub release.
5. Release artifacts must include checksums.

## Step 1: Inspect Existing CI And Scripts

Run:

```powershell
git status --short
Get-Content .github\workflows\ci.yml
Get-Content build.ps1
Get-Content scripts\package-release.ps1
if (Test-Path scripts\build-installer.ps1) { Get-Content scripts\build-installer.ps1 }
Get-Content pyproject.toml
Get-Content src\md_reader\__init__.py
```

Confirm:

- CI currently tests on Windows.
- `build.ps1` works locally.
- `scripts\package-release.ps1` writes a ZIP and `SHA256SUMS.txt`.
- `scripts\build-installer.ps1` exists from Phase 2.

If Phase 2 was not performed, stop and run Phase 2 first.

## Step 2: Add Release Notes Template

Create:

```text
docs\release-notes-template.md
```

Use:

```markdown
# MD Reader {version}

## Download

- Installer: `MDReader-v{version}-windows-x64-setup-unsigned.exe`
- Portable ZIP: `MDReader-v{version}-windows-x64-unsigned.zip`
- Checksums: `SHA256SUMS.txt`

## Install

Run the installer for normal use. Use the portable ZIP only when you want to extract and run MD Reader without installing.

## Notes

- This release is unsigned unless the installer filename does not include `unsigned`.
- Windows SmartScreen may warn on unsigned builds.
- The installer registers MD Reader as an available Markdown opener for the current Windows user.
```

## Step 3: Add Release Workflow

Create:

```text
.github\workflows\release.yml
```

Use this workflow:

```yaml
name: Release

on:
  push:
    tags:
      - "v*.*.*"
  workflow_dispatch:
    inputs:
      version:
        description: "Release version without leading v, for example 0.1.1"
        required: true
        type: string

permissions:
  contents: read

jobs:
  release:
    name: Build and publish Windows release
    runs-on: windows-latest
    permissions:
      contents: write

    steps:
      - name: Check out repository
        uses: actions/checkout@v4

      - name: Set release version
        id: version
        shell: pwsh
        run: |
          if ("${{ github.event_name }}" -eq "workflow_dispatch") {
            $version = "${{ inputs.version }}"
            $tag = "v$version"
          } else {
            $tag = "${{ github.ref_name }}"
            $version = $tag.TrimStart("v")
          }
          if (-not ($version -match '^\d+\.\d+\.\d+$')) {
            throw "Version must match MAJOR.MINOR.PATCH. Received: $version"
          }
          "version=$version" >> $env:GITHUB_OUTPUT
          "tag=$tag" >> $env:GITHUB_OUTPUT

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip

      - name: Install Python dependencies
        run: python -m pip install -r requirements.txt

      - name: Verify project version
        shell: pwsh
        run: |
          $expected = "${{ steps.version.outputs.version }}"
          $project = (Select-String -Path pyproject.toml -Pattern '^version\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
          $package = (Select-String -Path src\md_reader\__init__.py -Pattern '__version__\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
          if ($project -ne $expected) { throw "pyproject.toml version $project does not match release $expected" }
          if ($package -ne $expected) { throw "src\md_reader\__init__.py version $package does not match release $expected" }

      - name: Compile sources
        run: python -m compileall -q src tests scripts

      - name: Run tests
        run: python -m unittest discover -s tests -v

      - name: Build production app
        shell: pwsh
        run: .\build.ps1

      - name: Install Inno Setup
        shell: pwsh
        run: |
          choco install innosetup -y --no-progress
          $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
          if (-not (Test-Path -LiteralPath $iscc)) {
            throw "ISCC.exe was not found after installing Inno Setup"
          }

      - name: Build installer
        shell: pwsh
        run: .\scripts\build-installer.ps1 -Version "${{ steps.version.outputs.version }}"

      - name: Package portable release
        shell: pwsh
        run: .\scripts\package-release.ps1 -Version "${{ steps.version.outputs.version }}"

      - name: Prepare release notes
        shell: pwsh
        run: |
          $version = "${{ steps.version.outputs.version }}"
          $template = Get-Content docs\release-notes-template.md -Raw
          $notes = $template.Replace("{version}", $version)
          Set-Content -LiteralPath release\v$version\GITHUB_RELEASE_NOTES.md -Value $notes -Encoding UTF8

      - name: Publish GitHub release
        shell: pwsh
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          $version = "${{ steps.version.outputs.version }}"
          $tag = "${{ steps.version.outputs.tag }}"
          $root = "release\v$version"
          $assets = @(
            "$root\MDReader-v$version-windows-x64-setup-unsigned.exe",
            "$root\MDReader-v$version-windows-x64-unsigned.zip",
            "$root\SHA256SUMS.txt"
          )
          foreach ($asset in $assets) {
            if (-not (Test-Path -LiteralPath $asset)) {
              throw "Missing release asset: $asset"
            }
          }
          gh release create $tag $assets --title "MD Reader $tag" --notes-file "$root\GITHUB_RELEASE_NOTES.md" --verify-tag
```

The Chocolatey Inno Setup install is acceptable for CI because it runs on a fresh GitHub-hosted runner. If the project requires only official download channels later, replace this step with a pinned Inno Setup installer download and hash verification.

Manual `workflow_dispatch` runs still require the corresponding `v<version>` tag to exist because the publish step uses `gh release create --verify-tag`.

## Step 4: Add Manual Release Checklist

Create:

```text
docs\launch\manual-release-checklist.md
```

Use:

```markdown
# Manual Release Checklist

1. Confirm working tree is clean: `git status --short`.
2. Confirm version in `pyproject.toml`, `src\md_reader\__init__.py`, and `scripts\version-info.txt`.
3. Run tests: `.\.venv\Scripts\python.exe -m unittest discover -s tests -v`.
4. Run build: `.\build.ps1`.
5. Run installer build: `.\scripts\build-installer.ps1`.
6. Run package script: `.\scripts\package-release.ps1`.
7. Inspect `release\v<version>\SHA256SUMS.txt`.
8. Create and push tag: `git tag v<version>` then `git push origin v<version>`.
9. Confirm GitHub Actions release workflow completed successfully.
10. Download release assets from GitHub and perform Phase 5 clean-machine QA.
```

Use the actual version in the commands when executing the checklist.

## Step 5: Dry-Run The Workflow Locally

Run local equivalents:

```powershell
$version = (Select-String -Path pyproject.toml -Pattern '^version\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
.\.venv\Scripts\python.exe -m compileall -q src tests scripts
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\build.ps1
.\scripts\build-installer.ps1 -Version $version
.\scripts\package-release.ps1 -Version $version
Test-Path "release\v$version\MDReader-v$version-windows-x64-setup-unsigned.exe"
Test-Path "release\v$version\MDReader-v$version-windows-x64-unsigned.zip"
Test-Path "release\v$version\SHA256SUMS.txt"
```

All `Test-Path` commands must print `True`.

## Step 6: Validate Workflow Syntax

Run:

```powershell
git diff -- .github\workflows\release.yml
```

Check manually that:

- `permissions: contents: write` exists only on the release job.
- The workflow runs only on version tags and manual dispatch.
- Asset paths match `scripts\build-installer.ps1` and `scripts\package-release.ps1`.
- `gh release create` uses `--verify-tag`.

If GitHub CLI is installed locally, optionally validate expected command help:

```powershell
gh release create --help
```

## Phase Completion Criteria

This phase is complete only when:

- `.github\workflows\release.yml` exists.
- `docs\release-notes-template.md` exists.
- `docs\launch\manual-release-checklist.md` exists.
- Local dry-run commands produce installer, ZIP, and checksums.
- Workflow asset names match local artifact names exactly.

## Completion Report Format

```text
Phase 3 complete.
Verified:
- local tests: pass
- local build: pass
- local installer build: pass
- local package: pass
- release workflow syntax inspected: pass

Changed files:
- .github\workflows\release.yml
- docs\release-notes-template.md
- docs\launch\manual-release-checklist.md
```
