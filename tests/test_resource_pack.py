from pathlib import Path

from laoba.resource_pack import ResourcePack


def test_parse_and_extract(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    pack = ResourcePack(root / "assets" / "qualcomm_resource_pack.zip", tmp_path)
    assert len(pack.models) == 41
    assert "红魔" in pack.brands()
    pack.test_integrity()

    xiaomi = next(model for model in pack.models if model.loader.endswith("小米8e.melf"))
    extracted = pack.extract_loader(xiaomi)
    assert extracted.name == "小米8e.melf"
    assert extracted.stat().st_size > 1_000_000


def test_all_loaders_resolve(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    pack = ResourcePack(root / "assets" / "qualcomm_resource_pack.zip", tmp_path)
    for model in pack.models:
        assert pack.resolve_member(model.loader)
