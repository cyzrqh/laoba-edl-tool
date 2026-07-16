from pathlib import Path

import pytest

from laoba.commands import CommandValidationError, ConnectionOptions, EdlCommandBuilder
from laoba.resource_pack import ModelProfile


@pytest.fixture
def profile() -> ModelProfile:
    return ModelProfile(
        brand="测试",
        series="测试",
        name="测试机",
        storage="UFS",
        auth="None",
        loader="/loader.bin",
        digest="",
        description="",
    )


def test_build_printgpt(tmp_path: Path, profile: ModelProfile) -> None:
    loader = tmp_path / "loader.bin"
    loader.write_bytes(b"loader")
    builder = EdlCommandBuilder(profile, loader, ConnectionOptions(lun=0))
    command = builder.print_gpt()
    assert command[0] == "printgpt"
    assert "--memory=ufs" in command
    assert "--lun=0" in command
    assert any(item.startswith("--loader=") for item in command)


def test_invalid_partition(tmp_path: Path, profile: ModelProfile) -> None:
    loader = tmp_path / "loader.bin"
    loader.write_bytes(b"loader")
    builder = EdlCommandBuilder(profile, loader, ConnectionOptions())
    with pytest.raises(CommandValidationError):
        builder.erase_partition("../userdata")
