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
