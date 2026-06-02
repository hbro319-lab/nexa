# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for NEXA v2.0
Build with:  pyinstaller nexa.spec
"""

import os
import sys

block_cipher = None

# Collect all NEXA source files as data
datas = [
    ('nexa_config.json', '.'),
    ('nexa_interface.html', '.'),
]

# Hidden imports that PyInstaller might miss
hiddenimports = [
    'nexa_dispatcher',
    'nexa_api_bridge',
    'nexa_app_finder',
    'nexa_dispatch_server',
    'psutil',
    'requests',
    'json',
    'threading',
    'http.server',
    'urllib.parse',
    'dataclasses',
    'shlex',
    'textwrap',
]

# Windows-specific hidden imports
if sys.platform == 'win32':
    hiddenimports.extend([
        'winreg',
        'ctypes',
        'ctypes.wintypes',
    ])

a = Analysis(
    ['nexa.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'mediapipe',
        'cv2',
        'opencv-python',
        'PIL',
        'tkinter',
        'matplotlib',
        'numpy',
        'scipy',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='nexa',
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
    icon=None,
)
