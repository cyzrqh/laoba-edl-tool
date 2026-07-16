from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Sequence

from .commands import CommandValidationError, ConnectionOptions, EdlCommandBuilder
from .device_detection import detect_qualcomm_9008
from .paths import bundled_path, default_workspace, user_data_dir
from .resource_pack import ResourcePack, ResourcePackError


def _resource_pack() -> ResourcePack:
    pack = ResourcePack(
        bundled_path("assets", "qualcomm_resource_pack.zip"),
        user_data_dir() / "loader_cache",
    )
    pack.test_integrity()
    return pack


def _json(data: object) -> None:
    print(json.dumps(data, ensure_ascii=False))


def _connection(args: argparse.Namespace) -> ConnectionOptions:
    return ConnectionOptions(
        transport=args.transport,
        port_name=args.port or "",
        lun=args.lun,
    )


def _build_edl_args(args: argparse.Namespace) -> list[str]:
    pack = _resource_pack()
    if args.profile_index < 0 or args.profile_index >= len(pack.models):
        raise CommandValidationError("内置引导索引无效")
    profile = pack.models[args.profile_index]
    loader = pack.extract_loader(profile)
    builder = EdlCommandBuilder(profile, loader, _connection(args))

    if args.operation == "printgpt":
        return builder.print_gpt()
    if args.operation == "reset":
        return builder.reset()
    if args.operation == "read":
        return builder.read_partition(args.partition, args.output)
    if args.operation == "write":
        return builder.write_partition(args.partition, args.image)
    if args.operation == "erase":
        return builder.erase_partition(args.partition)
    if args.operation == "backup":
        return builder.backup_all(args.output_dir, args.skip)
    if args.operation == "flash-folder":
        return builder.flash_folder(args.image_dir)
    if args.operation == "qfil":
        return builder.qfil(args.rawprogram, args.patch, args.image_dir)
    raise CommandValidationError(f"不支持的操作：{args.operation}")


def _run_edl(edl_args: Sequence[str]) -> int:
    old_argv = sys.argv[:]
    old_cwd = os.getcwd()
    try:
        workspace = default_workspace()
        workspace.mkdir(parents=True, exist_ok=True)
        os.chdir(workspace)
        sys.argv = ["edl", *edl_args]
        import edlclient.edl as edl_module

        cli = edl_module.main(edl_module.args, edl_module.__name__)
        result = cli.run()
        return int(result) if isinstance(result, int) else 0
    finally:
        sys.argv = old_argv
        os.chdir(old_cwd)


def _extract_drivers(target: str) -> None:
    source = bundled_path("drivers", "Windows")
    destination = Path(target).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError("程序未包含 Windows 驱动")
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)
    print(str(destination))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="老八核心")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list-loaders")
    sub.add_parser("detect")

    extract = sub.add_parser("extract-drivers")
    extract.add_argument("--target", required=True)

    run = sub.add_parser("run")
    run.add_argument("--profile-index", type=int, required=True)
    run.add_argument("--transport", choices=("usb", "serial", "port"), default="usb")
    run.add_argument("--port", default="")
    run.add_argument("--lun", type=int)
    run.add_argument(
        "operation",
        choices=("printgpt", "reset", "read", "write", "erase", "backup", "flash-folder", "qfil"),
    )
    run.add_argument("--partition", default="")
    run.add_argument("--output", default="")
    run.add_argument("--image", default="")
    run.add_argument("--output-dir", default="")
    run.add_argument("--skip", default="userdata")
    run.add_argument("--image-dir", default="")
    run.add_argument("--rawprogram", default="")
    run.add_argument("--patch", default="")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "list-loaders":
            pack = _resource_pack()
            _json(
                [
                    {
                        "index": index,
                        "brand": model.brand,
                        "series": model.series,
                        "name": model.name,
                        "storage": model.storage,
                        "auth": model.auth,
                        "loader": model.loader,
                    }
                    for index, model in enumerate(pack.models)
                ]
            )
            return 0
        if args.command == "detect":
            _json(
                [
                    {"name": device.name, "pnp_device_id": device.pnp_device_id}
                    for device in detect_qualcomm_9008()
                ]
            )
            return 0
        if args.command == "extract-drivers":
            _extract_drivers(args.target)
            return 0
        if args.command == "run":
            return _run_edl(_build_edl_args(args))
    except (CommandValidationError, ResourcePackError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
