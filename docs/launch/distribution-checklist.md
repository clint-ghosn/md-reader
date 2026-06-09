# Distribution Checklist

1. Build installer, portable ZIP, and checksums.
2. Sign installer if a certificate is available.
3. Verify signed installer with `signtool verify /pa /v`.
4. Verify checksums with `Get-FileHash`.
5. Publish GitHub release through the release workflow.
6. Download assets from GitHub, not local `release\`.
7. Run Phase 5 clean-machine QA.
8. Confirm the GitHub Pages product page points users to the latest installer.
9. Draft a winget manifest only after QA passes.
10. Submit a winget manifest only after explicit user approval.
