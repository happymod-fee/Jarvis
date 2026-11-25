# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller specification file for VAX Desktop Voice Assistant.
Bundles the PySide6 UI, ONNX wake word models, and automation tools into a standalone Windows binary.
"""

import sys
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Base directory of the repository
BASE_DIR = os.path.abspath(SPECPATH)
ROOT_DIR = os.path.dirname(BASE_DIR)

# Collect openwakeword data models
oww_datas = collect_data_files("openwakeword")

datas = oww_datas + [
    (os.path.join(BASE_DIR, "plugins"), "vax/plugins"),
]

hiddenimports = (
    collect_submodules("vax") +
    collect_submodules("keyring") +
    [
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "sounddevice",
        "soundfile",
        "onnxruntime",
        "openwakeword",
        "openwakeword.model",
        "openwakeword.utils",
        "edge_tts",
        "google.genai",
        "openai",
        "anthropic",
        "httpx",
        "psutil",
        "pyautogui",
        "pyperclip",
        "send2trash",
        "deep_translator",
        "keyboard",
    ]
)

a = Analysis(
    [os.path.join(BASE_DIR, "main.py")],
    pathex=[ROOT_DIR, BASE_DIR],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="VAX_Voice_Assistant",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # Keeps console open for debug log inspection
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="VAX_Voice_Assistant",
)
