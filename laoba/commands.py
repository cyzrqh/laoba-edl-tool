from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

from .resource_pack import ModelProfile

_PARTITION_RE = re.compile(r"^[A-Za-z0-9_.:+-]{1,128}$")


class CommandValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ConnectionOptions:
    transport: str = "usb"  # usb | serial | port
    port_name: str = ""
    lun: Optional[int] = None


class EdlCommandBuilder:
    """Build a limited, flashing-oriented subset of bkerler/edl commands."""

    def __init__(
        self,
        profile: ModelProfile,
        loader_path: Path,
        connection: ConnectionOptions,
    ):
        self.profile = profile
        self.loader_path = Path(loader_path).resolve()
        self.connection = connection
        if not self.loader_path.is_file():
            raise CommandValidationError(f"引导文件不存在：{self.loader_path}")

    def _options(self) -> list[str]:
        options = [f"--loader={self.loader_path}"]
        storage = self.profile.storage.upper()
        if storage not in {"", "AUTO"}:
            options.append(f"--memory={storage.lower()}")
        if self.connection.lun is not None:
            if self.connection.lun < 0 or self.connection.lun > 255:
                raise CommandValidationError("LUN 必须在 0 到 255 之间")
            options.append(f"--lun={self.connection.lun}")
        if self.connection.transport == "serial":
            options.append("--serial")
        elif self.connection.transport == "port":
            if not self.connection.port_name.strip():
                raise CommandValidationError("请选择或填写串口名")
            options.append(f"--portname={self.connection.port_name.strip()}")
        elif self.connection.transport != "usb":
            raise CommandValidationError("未知连接方式")
        return options

    @staticmethod
    def _partition(name: str) -> str:
        value = name.strip()
        if not _PARTITION_RE.fullmatch(value):
            raise CommandValidationError(
                "分区名只能包含字母、数字、下划线、点、冒号、加号和连字符"
            )
        return value

    @staticmethod
    def _existing_file(path: Union[str, Path], label: str) -> str:
        file_path = Path(path).expanduser().resolve()
        if not file_path.is_file():
            raise CommandValidationError(f"{label}不存在：{file_path}")
        return str(file_path)

    @staticmethod
    def _existing_dir(path: Union[str, Path], label: str) -> str:
        dir_path = Path(path).expanduser().resolve()
        if not dir_path.is_dir():
            raise CommandValidationError(f"{label}不存在：{dir_path}")
        return str(dir_path)

    @staticmethod
    def _output_file(path: Union[str, Path], label: str) -> str:
        file_path = Path(path).expanduser().resolve()
        file_path.parent.mkdir(parents=True, exist_ok=True)
        if file_path.exists() and file_path.is_dir():
            raise CommandValidationError(f"{label}不能是文件夹：{file_path}")
        return str(file_path)

    def print_gpt(self) -> list[str]:
        return ["printgpt", *self._options()]

    def reset(self) -> list[str]:
        return ["reset", *self._options()]

    def read_partition(self, partition: str, output_file: Union[str, Path]) -> list[str]:
        return [
            "r",
            self._partition(partition),
            self._output_file(output_file, "输出文件"),
            *self._options(),
        ]

    def write_partition(self, partition: str, image_file: Union[str, Path]) -> list[str]:
        return [
            "w",
            self._partition(partition),
            self._existing_file(image_file, "镜像文件"),
            *self._options(),
        ]

    def erase_partition(self, partition: str) -> list[str]:
        return ["e", self._partition(partition), *self._options()]

    def backup_all(self, output_dir: Union[str, Path], skip: str = "userdata") -> list[str]:
        directory = Path(output_dir).expanduser().resolve()
        directory.mkdir(parents=True, exist_ok=True)
        command = ["rl", str(directory)]
        skip_items = [item.strip() for item in skip.split(",") if item.strip()]
        if skip_items:
            for item in skip_items:
                self._partition(item)
            command.append(f"--skip={','.join(skip_items)}")
        command.append("--genxml")
        return [*command, *self._options()]

    def flash_folder(self, image_dir: Union[str, Path]) -> list[str]:
        return ["wl", self._existing_dir(image_dir, "镜像目录"), *self._options()]

    def qfil(
        self,
        rawprogram_xml: Union[str, Path],
        patch_xml: Union[str, Path],
        image_dir: Union[str, Path],
    ) -> list[str]:
        return [
            "qfil",
            self._existing_file(rawprogram_xml, "rawprogram XML"),
            self._existing_file(patch_xml, "patch XML"),
            self._existing_dir(image_dir, "镜像目录"),
            *self._options(),
        ]
