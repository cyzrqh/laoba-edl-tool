from __future__ import annotations

import argparse
import shutil
import tempfile
from pathlib import Path

import py7zr


def score(path: Path, architecture: str) -> tuple[int, int, str]:
    text = str(path).replace("\\", "/").casefold()
    wanted = ["mingw64", "x64", "amd64"] if architecture == "x64" else ["mingw32", "x86", "win32"]
    unwanted = ["x86", "win32", "mingw32"] if architecture == "x64" else ["x64", "amd64", "mingw64"]
    points = 0
    for index, token in enumerate(wanted):
        if token in text:
            points += 30 - index
    for token in unwanted:
        if token in text:
            points -= 50
    if "/dll/" in text:
        points += 10
    if "debug" in text:
        points -= 20
    return points, -len(text), text


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--architecture", choices=("x64", "x86"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if not args.archive.is_file():
        raise SystemExit(f"找不到上游 libusb 压缩包：{args.archive}")

    with tempfile.TemporaryDirectory(prefix="laoba-libusb-") as temp_dir:
        temp = Path(temp_dir)
        with py7zr.SevenZipFile(args.archive, mode="r") as archive:
            archive.extractall(path=temp)
        candidates = list(temp.rglob("libusb-1.0.dll"))
        if not candidates:
            raise SystemExit("上游 libusb 压缩包中没有 libusb-1.0.dll")
        selected = max(candidates, key=lambda item: score(item, args.architecture))
        selected_score = score(selected, args.architecture)[0]
        if selected_score < 0:
            listing = "\n".join(str(item.relative_to(temp)) for item in candidates)
            raise SystemExit(
                f"无法为 {args.architecture} 可靠选择 libusb-1.0.dll。候选：\n{listing}"
            )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(selected, args.output)
        print(f"已选择 {selected.relative_to(temp)} -> {args.output}")


if __name__ == "__main__":
    main()
