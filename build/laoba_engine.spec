# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import os
import sys

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH).resolve().parent
VENDOR_EDL = ROOT / "vendor" / "edl"
if not VENDOR_EDL.exists():
    raise SystemExit(f"缺少 vendor/edl：{VENDOR_EDL}")

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(VENDOR_EDL))

edl_datas, edl_binaries, edl_hiddenimports = collect_all("edlclient")
architecture = os.environ.get("LAOBA_ARCH", "x64")
runtime_libusb = ROOT / "build" / f"runtime-dll-{architecture}" / "libusb-1.0.dll"
if not runtime_libusb.exists():
    raise SystemExit(f"缺少运行时 libusb DLL：{runtime_libusb}")

binaries = list(edl_binaries)
binaries.append((str(runtime_libusb), "."))
hiddenimports = sorted(set(
    edl_hiddenimports
    + collect_submodules("edlclient")
    + [
        "usb.backend.libusb1",
        "serial.tools.list_ports",
        "Cryptodome",
        "Crypto",
        "lxml.etree",
    ]
))

datas = list(edl_datas)
datas += [
    (str(ROOT / "assets" / "qualcomm_resource_pack.zip"), "assets"),
    (str(ROOT / "assets" / "RESOURCE_SHA256.txt"), "assets"),
    (str(ROOT / "assets" / "resource_manifest.json"), "assets"),
    (str(ROOT / "LICENSE"), "."),
    (str(ROOT / "THIRD_PARTY_NOTICES.md"), "."),
]

driver_dir = VENDOR_EDL / "Drivers" / "Windows"
if driver_dir.exists():
    datas.append((str(driver_dir), "drivers/Windows"))

analysis = Analysis(
    [str(ROOT / "engine.py")],
    pathex=[str(ROOT), str(VENDOR_EDL)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "tkinter", "customtkinter"],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name="老八核心",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "assets" / "app_icon.ico"),
    version=str(ROOT / "build" / "version_info.txt"),
    uac_admin=False,
)
