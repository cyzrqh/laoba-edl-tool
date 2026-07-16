from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR_NAME = "老八刷机工具"


def bundled_path(*parts: str) -> Path:
    """Return a path inside source tree or a PyInstaller bundle."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return base.joinpath(*parts)


def user_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        path = Path(base) / APP_DIR_NAME
    else:
        path = Path.home() / f".{APP_DIR_NAME}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_workspace() -> Path:
    documents = Path.home() / "Documents"
    base = documents if documents.exists() else Path.home()
    path = base / APP_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path
