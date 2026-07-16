from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class DetectedDevice:
    name: str
    pnp_device_id: str


def detect_qualcomm_9008() -> list[DetectedDevice]:
    if os.name != "nt":
        return []
    command = r"""
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$items = Get-CimInstance Win32_PnPEntity | Where-Object {
  $_.PNPDeviceID -match 'VID_05C6&PID_9008' -or
  $_.Name -match 'QHSUSB|QDLoader 9008|Qualcomm.*9008'
} | Select-Object Name, PNPDeviceID
$items | ConvertTo-Json -Compress
"""
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                command,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=12,
            creationflags=creationflags,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    payload = completed.stdout.strip()
    if not payload or payload == "null":
        return []
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        data = [data]
    devices: list[DetectedDevice] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        devices.append(
            DetectedDevice(
                name=str(item.get("Name") or "Qualcomm 9008"),
                pnp_device_id=str(item.get("PNPDeviceID") or ""),
            )
        )
    return devices
