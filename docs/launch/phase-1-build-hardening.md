# Phase 1: Build Hardening Codex Runbook

**Codex goal:** Make MD Reader produce a clean, repeatable Windows x64 application bundle from a fresh checkout.

**Phase output:** A verified `dist\MDReader\MDReader.exe` folder build and a release ZIP from `scripts\package-release.ps1`.

**Repo root:** `D:\Dev\workspace\md-reader`

**Do not change:** Application UI behavior, Markdown rendering behavior, file association behavior, or installer behavior. Those belong to later phases.

## Current Project Context

MD Reader is a Python desktop app using PySide6 and PyInstaller. The relevant launch files already exist:

- `pyproject.toml`: project metadata and Python package entry point.
- `requirements.txt`: runtime plus build requirements.
- `build.ps1`: current PyInstaller build entrypoint.
- `MDReader.spec`: PyInstaller spec file for the production build.
- `scripts\version-info.txt`: Windows version metadata consumed by PyInstaller.
- `scripts\make-icon.ps1`: icon generation helper used by `build.ps1`.
- `scripts\package-release.ps1`: packages `dist\MDReader` into a release ZIP and writes checksums.
- `.github\workflows\ci.yml`: Windows CI build/test workflow.
- `.gitignore`: already excludes `build/`, `dist/`, `release/`, `__pycache__/`, and `*.pyc.*`.

## Technical References

- PyInstaller creates the bundled application under `dist` and accepts either command-line options or a spec file. Official docs: https://pyinstaller.org/en/latest/usage.html
- GitHub-hosted Windows runners are available through `runs-on: windows-latest`. Official docs: https://docs.github.com/en/actions/how-tos/using-github-hosted-runners/using-github-hosted-runners

## Execution Rules For Codex

1. Work from the repo root.
2. Preserve user changes. Start with `git status --short` and do not revert unrelated edits.
3. Use `apply_patch` for file edits.
4. Prefer the existing `build.ps1` and `scripts\package-release.ps1` entrypoints over adding a new build system.
5. Keep this phase focused on build reproducibility and package verification.

## Step 1: Inspect Baseline State

Run:

```powershell
git status --short
rg --files -g "pyproject.toml" -g "requirements.txt" -g "build.ps1" -g "MDReader.spec" -g "scripts/**" -g ".github/workflows/**" -g "tests/**" -g "LICENSE" -g "THIRD_PARTY_NOTICES.md"
Get-Content pyproject.toml
Get-Content requirements.txt
Get-Content build.ps1
Get-Content MDReader.spec
Get-Content scripts\package-release.ps1
Get-Content scripts\version-info.txt
Get-Content .github\workflows\ci.yml
```

Confirm:

- `pyproject.toml` version matches `src\md_reader\__init__.py`.
- `scripts\version-info.txt` uses the same version with four numeric parts.
- `build.ps1` includes the icon, Mermaid bundle, Mermaid license, and Qt WebEngine hidden imports.
- `scripts\package-release.ps1` includes `README.md`, `LICENSE`, `THIRD_PARTY_NOTICES.md`, `install.ps1`, and `uninstall.ps1`.
- `LICENSE` and `THIRD_PARTY_NOTICES.md` exist before packaging.

If any version values differ, update the stale value only. Do not bump the release number unless the user explicitly asks.

## Step 2: Remove Tracked Cache Artifacts If Present

The repo contains `.gitignore` rules for Python caches, but previous tracked cache files may still exist.

Run:

```powershell
git ls-files "*__pycache__*" "*.pyc" "*.pyc.*"
```

If output is empty, do nothing.

If tracked cache files are listed, remove them from git tracking without deleting the user's working files:

```powershell
git rm --cached --quiet -- <each-listed-cache-path>
```

Use exact paths from `git ls-files`. Do not run recursive delete commands in this phase.

## Step 3: Verify Local Python Environment

Run:

```powershell
py -3.11 --version
```

If Python 3.11 is unavailable, run:

```powershell
py --version
```

Use the installed Python if it satisfies `requires-python = ">=3.10"` in `pyproject.toml`. If no compatible Python exists, stop and report that Python 3.10 or newer must be installed before this phase can complete.

Create or reuse the local virtual environment:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

If dependency installation fails due to network restrictions, request escalation and rerun the same install command with approval.

## Step 4: Run Source Verification

Run:

```powershell
.\.venv\Scripts\python.exe -m compileall -q src tests scripts
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Expected result:

- `compileall` exits `0`.
- `unittest` exits `0`.

If tests fail, use systematic debugging before changing code. Fix only failures that block building or packaging.

## Step 5: Align PyInstaller Build Entry Point

Open `build.ps1` and `MDReader.spec`.

The preferred phase-1 outcome is:

- `build.ps1` remains the public build command.
- `MDReader.spec` remains checked in as the canonical PyInstaller build definition.
- `build.ps1` invokes PyInstaller through the venv Python where possible.

If `build.ps1` and `MDReader.spec` diverge, align them by updating `build.ps1` to use the spec file:

```powershell
& $Python -m PyInstaller --noconfirm --clean "MDReader.spec"
```

Where `$Python` is resolved like this near the top of `build.ps1`:

```powershell
$VenvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (Test-Path -LiteralPath $VenvPython) {
    $Python = $VenvPython
} else {
    $Python = "python"
}
```

Keep the existing running-process guard and cache cleanup logic. Keep `scripts\make-icon.ps1` before PyInstaller.

If you keep the existing command-line PyInstaller invocation instead of switching to the spec file, confirm the command-line arguments match `MDReader.spec` exactly for:

- app name
- icon
- version file
- asset datas
- hidden imports
- windowed mode

## Step 6: Build The App Bundle

Run the approved build command from the repo root:

```powershell
.\build.ps1
```

Expected output includes:

```text
Built dist\MDReader\MDReader.exe
```

Then verify the expected files:

```powershell
Test-Path dist\MDReader\MDReader.exe
Test-Path dist\MDReader\_internal\assets\mdreader.ico
Test-Path dist\MDReader\_internal\assets\mermaid.min.js
Test-Path dist\MDReader\_internal\assets\mermaid.LICENSE.txt
```

All four commands must print `True`.

## Step 7: Smoke Launch Without Opening The GUI Permanently

Run:

```powershell
$exe = Resolve-Path .\dist\MDReader\MDReader.exe
$process = Start-Process -FilePath $exe -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 5
if ($process.HasExited) { throw "MDReader exited early with code $($process.ExitCode)" }
Stop-Process -Id $process.Id
```

If GUI launch fails because the environment cannot start Windows desktop applications, report that limitation and continue to package verification only if the executable exists.

## Step 8: Package The Portable Release ZIP

Run:

```powershell
.\scripts\package-release.ps1
```

Expected output includes:

- `Release root: ...\release\v0.1.0`
- `ZIP: ...MDReader-v0.1.0-windows-x64-unsigned.zip`
- `Checksums: ...SHA256SUMS.txt`

Verify:

```powershell
Test-Path release\v0.1.0\MDReader-v0.1.0-windows-x64-unsigned.zip
Test-Path release\v0.1.0\SHA256SUMS.txt
Get-Content release\v0.1.0\SHA256SUMS.txt
```

The checksum file must include at least the ZIP and `MDReader\MDReader.exe`.

## Step 9: Update README Build Instructions If Needed

If build or package commands changed, update `README.md` so the Build section contains the actual commands:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\build.ps1
.\scripts\package-release.ps1
```

Do not add installer instructions in this phase.

## Phase Completion Criteria

This phase is complete only when:

- `python -m compileall -q src tests scripts` passes.
- `python -m unittest discover -s tests -v` passes.
- `.\build.ps1` produces `dist\MDReader\MDReader.exe`.
- `.\scripts\package-release.ps1` produces a ZIP and checksums.
- Any tracked cache files were removed from git tracking.
- README build instructions match the verified commands.

## Completion Report Format

When finished, report:

```text
Phase 1 complete.
Verified:
- compileall: pass
- unit tests: pass
- build.ps1: pass
- package-release.ps1: pass

Changed files:
- <actual changed path>

Release artifact:
- <actual ZIP path>
```

