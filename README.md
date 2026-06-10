# MD Reader

A small Python Windows desktop app for reading and editing Markdown files.

## Download and install

For normal use, download the installer from the MD Reader product page:

```text
https://clint-ghosn.github.io/md-reader/
```

The current installer asset is:

```text
MDReader-v0.1.1-windows-x64-setup-unsigned.exe
```

Portable builds are also published as:

```text
MDReader-v0.1.1-windows-x64-unsigned.zip
```

The installer registers MD Reader as an available Markdown opener for the current Windows user. If Windows keeps another default app for `.md` files, choose MD Reader from **Settings > Apps > Default apps**.

MD Reader can be launched on its own like a text editor. From there, use:

- `File > New` to start a new Markdown file.
- `File > Open` to open one Markdown file without showing sibling files.
- `File > Open Folder` to show the left Markdown file drawer for that folder.
- `File > Save` or `File > Save As` to write Markdown files.
- `File > Export HTML` to export the current document as a standalone HTML file.
- `Help > Markdown Help` for beginner-friendly Markdown guidance.

The editor includes a Markdown toolbar for headings, bold, italic, links, images, lists, quotes, code blocks, and starter tables. Window layout, splitter position, and recent files are remembered between sessions.

Mermaid diagrams in fenced code blocks render in the preview:

````markdown
```mermaid
graph TD
  A-->B
```
````

Mermaid support is bundled in `src/md_reader/assets/mermaid.min.js` for offline use. When updating Mermaid, replace that pinned browser bundle and update `src/md_reader/assets/mermaid.LICENSE.txt` from the same upstream version.

## Build

From this directory:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
.\build.ps1
```

The executable is written to:

```text
dist\MDReader\MDReader.exe
```

To package a portable release ZIP:

```powershell
.\scripts\package-release.ps1
```

To build the installer after installing Inno Setup 6:

```powershell
.\scripts\build-installer.ps1
```

## Verify downloads

After downloading a release asset and `SHA256SUMS.txt`, verify the file hash in PowerShell:

```powershell
Get-FileHash .\MDReader-v0.1.1-windows-x64-setup-unsigned.exe -Algorithm SHA256
Get-Content .\SHA256SUMS.txt
```

The hash printed by `Get-FileHash` should match the line for the downloaded file.

## Install file association

After building:

```powershell
.\install.ps1
```

This registers `.md` files for the current user so double-clicking a Markdown file opens it in MD Reader.

Run `uninstall.ps1` to remove MD Reader's per-user registration. The uninstall script removes MD Reader's ProgID and OpenWith registration without deleting the entire `.md` registry key.

## Explorer Preview Pane

Windows Explorer's formatted preview pane is powered by COM preview handlers. A formatted Markdown preview requires a real preview handler registered under the file type's `shellex` preview handler key.

This project includes:

- A working Markdown viewer executable.
- Per-user `.md` file association.
- A documented preview-pane registration target in `install.ps1`.

The preview handler itself must be a Windows COM component implementing `IPreviewHandler`, `IInitializeWithFile` or `IInitializeWithStream`, `IObjectWithSite`, and `IOleWindow`. Python can build the desktop executable reliably, but a production Explorer preview handler is usually shipped as a native or managed COM component because Explorer hosts it through `Prevhost.exe`.
