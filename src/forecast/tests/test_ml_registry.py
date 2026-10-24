from __future__ import annotations

from pathlib import Path

import pytest

from forecast.ml.registry import LocalModelRegistry


def test_register_and_alias_roundtrip(tmp_path: Path) -> None:
    source = tmp_path / "model.pt"
    source.write_bytes(b"checkpoint")
    registry = LocalModelRegistry(tmp_path / "registry.json")
    version = registry.register(source, {"WAPE": 0.2}, alias="challenger")
    assert version.version == 1
    assert registry.alias_of("challenger") == 1
    resolved = registry.resolve("challenger")
    assert resolved is not None
    assert resolved.read_bytes() == b"checkpoint"
    assert registry.resolve("champion") is None


def test_promote_sets_champion_alias(tmp_path: Path) -> None:
    source = tmp_path / "model.pt"
    source.write_bytes(b"checkpoint")
    registry = LocalModelRegistry(tmp_path / "registry.json")
    first = registry.register(source, {"WAPE": 0.3}, alias="challenger")
    second = registry.register(source, {"WAPE": 0.2}, alias="challenger")
    assert second.version == 2
    registry.promote(second.version, "champion")
    assert registry.alias_of("champion") == 2
    assert registry.alias_of("challenger") == 2
    assert registry.versions()[0].version == first.version


def test_unknown_alias_and_version(tmp_path: Path) -> None:
    registry = LocalModelRegistry(tmp_path / "registry.json")
    assert registry.resolve("champion") is None
    with pytest.raises(KeyError):
        registry.set_alias("champion", 99)


def test_missing_source_raises(tmp_path: Path) -> None:
    registry = LocalModelRegistry(tmp_path / "registry.json")
    with pytest.raises(FileNotFoundError):
        registry.register(tmp_path / "missing.pt", {})
