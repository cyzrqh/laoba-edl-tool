from __future__ import annotations

import hashlib
import os
import re
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable


@dataclass(frozen=True)
class PackageInfo:
    publisher: str
    publish_date: str
    version: str
    tip: str
    package_type: str


@dataclass(frozen=True)
class ModelProfile:
    brand: str
    series: str
    name: str
    storage: str
    auth: str
    loader: str
    digest: str
    description: str

    @property
    def display_name(self) -> str:
        return self.name


class ResourcePackError(RuntimeError):
    pass


def _normalise_member(name: str) -> str:
    return name.replace("\\", "/").lstrip("/")


def _strip_package_root(name: str) -> str:
    normalised = _normalise_member(name)
    parts = PurePosixPath(normalised).parts
    if len(parts) > 1:
        return "/".join(parts[1:])
    return normalised


def _safe_requested_path(value: str) -> str:
    normalised = value.replace("\\", "/").lstrip("/")
    parts = PurePosixPath(normalised).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ResourcePackError(f"资源路径不安全：{value}")
    return "/".join(parts)


def _ascii_tail(filename: str) -> str:
    match = re.search(r"([A-Za-z0-9+_.-]+)$", filename)
    return match.group(1).casefold() if match else filename.casefold()


class ResourcePack:
    """Read the uploaded GeekFlashPacket ZIP without extracting it wholesale."""

    def __init__(self, zip_path: Path, cache_dir: Path):
        self.zip_path = Path(zip_path)
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        if not self.zip_path.is_file():
            raise ResourcePackError(f"找不到内置资源包：{self.zip_path}")

        self.package_info, self.models = self._parse_config()
        self._member_index = self._build_member_index()

    @property
    def sha256(self) -> str:
        digest = hashlib.sha256()
        with self.zip_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def test_integrity(self) -> None:
        try:
            with zipfile.ZipFile(self.zip_path) as archive:
                bad = archive.testzip()
        except (OSError, zipfile.BadZipFile) as exc:
            raise ResourcePackError(f"资源包无法读取：{exc}") from exc
        if bad:
            raise ResourcePackError(f"资源包校验失败，损坏条目：{bad}")

    def brands(self) -> list[str]:
        return list(dict.fromkeys(model.brand for model in self.models))

    def series_for(self, brand: str) -> list[str]:
        return list(
            dict.fromkeys(model.series for model in self.models if model.brand == brand)
        )

    def models_for(self, brand: str, series: str) -> list[ModelProfile]:
        return [
            model
            for model in self.models
            if model.brand == brand and model.series == series
        ]

    def _find_config_member(self, archive: zipfile.ZipFile) -> str:
        candidates = [
            name
            for name in archive.namelist()
            if _normalise_member(name).casefold().endswith("/config.xml")
            or _normalise_member(name).casefold() == "config.xml"
        ]
        if len(candidates) != 1:
            raise ResourcePackError(
                f"资源包中 Config.xml 数量异常：{len(candidates)}"
            )
        return candidates[0]

    def _parse_config(self) -> tuple[PackageInfo, list[ModelProfile]]:
        try:
            with zipfile.ZipFile(self.zip_path) as archive:
                config_member = self._find_config_member(archive)
                config_data = archive.read(config_member)
        except (OSError, zipfile.BadZipFile, KeyError) as exc:
            raise ResourcePackError(f"读取资源配置失败：{exc}") from exc

        try:
            root = ET.fromstring(config_data)
        except ET.ParseError as exc:
            raise ResourcePackError(f"Config.xml 格式错误：{exc}") from exc

        packet = root.find("PacketInfo")
        if packet is None:
            raise ResourcePackError("Config.xml 缺少 PacketInfo")
        info = PackageInfo(
            publisher=packet.get("Publisher", ""),
            publish_date=packet.get("PublishDate", ""),
            version=packet.get("PublishVersion", ""),
            tip=packet.get("Tip", ""),
            package_type=packet.get("Type", ""),
        )

        models: list[ModelProfile] = []
        for brand_node in root.findall("Brand"):
            brand = brand_node.get("Name", "未命名品牌")
            for series_node in brand_node.findall("Series"):
                series = series_node.get("Name", "未命名系列")
                for model_node in series_node.findall("Model"):
                    loader = model_node.get("Loader", "")
                    if not loader:
                        continue
                    models.append(
                        ModelProfile(
                            brand=brand,
                            series=series,
                            name=model_node.get("Name", "未命名机型"),
                            storage=model_node.get("Storage", "AUTO").upper(),
                            auth=model_node.get("Auth", "None"),
                            loader=loader,
                            digest=model_node.get("Digest", ""),
                            description=model_node.get("Description", ""),
                        )
                    )
        if not models:
            raise ResourcePackError("资源包中没有可用机型")
        return info, models

    def _build_member_index(self) -> list[tuple[str, str]]:
        try:
            with zipfile.ZipFile(self.zip_path) as archive:
                return [
                    (member, _strip_package_root(member))
                    for member in archive.namelist()
                    if not member.endswith(("/", "\\"))
                ]
        except (OSError, zipfile.BadZipFile) as exc:
            raise ResourcePackError(f"建立资源索引失败：{exc}") from exc

    def resolve_member(self, requested_loader: str) -> str:
        requested = _safe_requested_path(requested_loader)
        requested_cf = requested.casefold()

        exact = [
            original
            for original, stripped in self._member_index
            if stripped.casefold() == requested_cf
        ]
        if len(exact) == 1:
            return exact[0]

        req_path = PurePosixPath(requested)
        req_parent = str(req_path.parent).casefold()
        req_tail = _ascii_tail(req_path.name)
        fallback: list[str] = []
        for original, stripped in self._member_index:
            candidate = PurePosixPath(stripped)
            if str(candidate.parent).casefold() != req_parent:
                continue
            if candidate.name.casefold().endswith(req_tail):
                fallback.append(original)
        if len(fallback) == 1:
            return fallback[0]

        raise ResourcePackError(
            f"无法唯一匹配引导文件：{requested_loader}（候选 {len(fallback)} 个）"
        )

    def extract_loader(self, profile: ModelProfile) -> Path:
        requested = _safe_requested_path(profile.loader)
        member = self.resolve_member(requested)
        requested_path = PurePosixPath(requested)

        try:
            with zipfile.ZipFile(self.zip_path) as archive:
                payload = archive.read(member)
        except (OSError, zipfile.BadZipFile, KeyError) as exc:
            raise ResourcePackError(f"提取引导文件失败：{exc}") from exc

        content_hash = hashlib.sha256(payload).hexdigest()
        output_dir = self.cache_dir / content_hash[:16]
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / requested_path.name

        if output_path.exists() and output_path.stat().st_size == len(payload):
            return output_path

        fd, temp_name = tempfile.mkstemp(prefix="loader-", dir=output_dir)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, output_path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
        return output_path

    def iter_models(self) -> Iterable[ModelProfile]:
        return iter(self.models)
