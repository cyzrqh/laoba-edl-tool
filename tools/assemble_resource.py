from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="重组老八刷机工具的内置高通资源包")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "assets" / "resource_parts" / "parts.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "assets" / "qualcomm_resource_pack.zip",
    )
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    expected_size = int(manifest["size"])
    expected_sha = str(manifest["sha256"]).lower()
    parts = [args.manifest.parent / name for name in manifest["parts"]]

    if args.output.is_file() and args.output.stat().st_size == expected_size:
        if sha256(args.output) == expected_sha:
            print(f"资源包已存在且校验通过：{args.output}")
            return

    missing = [str(path) for path in parts if not path.is_file()]
    if missing:
        raise SystemExit("缺少资源分片：\n" + "\n".join(missing))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix="resource-", suffix=".zip", dir=args.output.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            for part in parts:
                with part.open("rb") as source:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        temporary = Path(temporary_name)
        actual_size = temporary.stat().st_size
        actual_sha = sha256(temporary)
        if actual_size != expected_size or actual_sha != expected_sha:
            raise SystemExit(
                "资源包重组校验失败："
                f"size={actual_size}/{expected_size}, sha256={actual_sha}/{expected_sha}"
            )
        os.replace(temporary, args.output)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)

    print(f"资源包重组完成：{args.output}")


if __name__ == "__main__":
    main()
