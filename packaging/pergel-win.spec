# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Pergel — Windows build
# Usage: pyinstaller pergel-win.spec

a = Analysis(
    ['../src/cli.py'],
    pathex=['..'],
    binaries=[],
    datas=[
        ('../src/brand/i18n_data.json', 'src/brand'),
        ('../docs', 'docs'),
    ],
    hiddenimports=[
        'src.api.server', 'src.api.web_ui', 'src.api.session_replay',
        'src.api.webmcp', 'src.api.extract',
        'src.brand.vane_app', 'src.brand.render', 'src.brand.i18n',
        'src.browser_engine.*', 'src.router.*', 'src.search.*',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'pandas'],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='pergel',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='../assets/pergel.ico',
)
