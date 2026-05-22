# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['src\\md_reader\\__main__.py'],
    pathex=['src'],
    binaries=[],
    datas=[('src\\md_reader\\assets\\mdreader.ico', 'assets'), ('src\\md_reader\\assets\\mermaid.min.js', 'assets'), ('src\\md_reader\\assets\\mermaid.LICENSE.txt', 'assets')],
    hiddenimports=['PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineQuick'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MDReader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='scripts\\version-info.txt',
    icon=['src\\md_reader\\assets\\mdreader.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='MDReader',
)
