# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import os
import sys

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH).resolve().parent.parent
VENDOR_EDL = ROOT / "vendor" / "edl"
if not VENDOR_EDL.exists():
    raise SystemExit("缺少 vendor/edl。请先运行 build/build_windows.ps1。")

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(VENDOR_EDL))

edl_datas, edl_binaries, edl_hiddenimports = collect_all("edlclient")
architecture = os.environ.get("LAOBA_ARCH", "x64")
runtime_libusb = ROOT / "build" / f"runtime-dll-{architecture}" / "libusb-1.0.dll"
if not runtime_libusb.exists():
    raise SystemExit(f"缺少运行时 libusb DLL：{runtime_libusb}")
edl_binaries.append((str(runtime_libusb), "."))
hiddenimports = sorted(set(edl_hiddenimports + collect_submodules("edlclient") + [
    "usb.backend.libusb1",
    "serial.tools.list_ports",
    "Cryptodome",
    "Crypto",
    "lxml.etree",
]))

datas = list(edl_datas)
datas += [
    (str(ROOT / "assets" / "app_icon.png"), "assets"),
    (str(ROOT / "assets" / "app_icon.ico"), "assets"),
    (str(ROOT / "assets" / "qualcomm_resource_pack.zip"), "assets"),
    (str(ROOT / "assets" / "RESOURCE_SHA256.txt"), "assets"),
    (str(ROOT / "assets" / "resource_manifest.json"), "assets"),
    (str(ROOT / "LICENSE"), "."),
    (str(ROOT / "THIRD_PARTY_NOTICES.md"), "."),
]

driver_dir = VENDOR_EDL / "Drivers" / "Windows"
if driver_dir.exists():
    datas.append((str(driver_dir), "drivers/Windows"))

upstream_license = VENDOR_EDL / "LICENSE"
upstream_readme = VENDOR_EDL / "README.md"
if upstream_license.exists():
    datas.append((str(upstream_license), "licenses/bkerler-edl"))
if upstream_readme.exists():
    datas.append((str(upstream_readme), "licenses/bkerler-edl"))

analysis = Analysis(
    [str(ROOT / "app.py")],
    pathex=[str(ROOT), str(VENDOR_EDL)],
    binaries=edl_binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest"],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="老八",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "assets" / "app_icon.ico"),
    version=str(ROOT / "build" / "version_info.txt"),
    uac_admin=False,
)

collection = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="老八",
)
