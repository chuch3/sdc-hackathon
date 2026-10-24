from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class ModelVersion:
    version: int
    checkpoint: str
    metrics: Mapping[str, float]
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "checkpoint": self.checkpoint,
            "metrics": dict(self.metrics),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ModelVersion":
        return cls(
            version=int(raw["version"]),
            checkpoint=str(raw["checkpoint"]),
            metrics={
                str(key): float(value)
                for key, value in (raw.get("metrics") or {}).items()
            },
            created_at=str(raw.get("created_at", "")),
        )


class LocalModelRegistry:
    """Offline registry with MLflow-style aliases.

    The file layout mirrors the alias semantics used by the remote MLflow
    registry so the demo works without network access.
    """

    def __init__(
        self,
        path: str | Path,
        model_name: str = "demand_forecaster",
    ) -> None:
        self.path = Path(path)
        self.model_name = model_name

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {
                "model_name": self.model_name,
                "versions": [],
                "aliases": {},
            }
        payload = json.loads(self.path.read_text())
        payload.setdefault("model_name", self.model_name)
        payload.setdefault("versions", [])
        payload.setdefault("aliases", {})
        return payload

    def _save(self, payload: Mapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True))
        temporary.replace(self.path)

    def versions(self) -> list[ModelVersion]:
        return [
            ModelVersion.from_dict(raw)
            for raw in self._load().get("versions", [])
        ]

    def register(
        self,
        checkpoint_path: str | Path,
        metrics: Mapping[str, float],
        alias: str | None = None,
    ) -> ModelVersion:
        source = Path(checkpoint_path)
        if not source.exists():
            raise FileNotFoundError(f"checkpoint not found: {source}")
        payload = self._load()
        version_number = max(
            (int(item["version"]) for item in payload["versions"]),
            default=0,
        ) + 1
        relative = (
            Path("registry")
            / self.model_name
            / f"v{version_number}"
            / source.name
        )
        destination = self.path.parent / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        version = ModelVersion(
            version=version_number,
            checkpoint=str(relative),
            metrics={key: float(value) for key, value in metrics.items()},
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        payload["versions"].append(version.to_dict())
        if alias:
            payload["aliases"][alias] = version_number
        self._save(payload)
        return version

    def alias_of(self, alias: str) -> int | None:
        value = self._load()["aliases"].get(alias)
        return None if value is None else int(value)

    def resolve(self, alias: str) -> Path | None:
        version_number = self.alias_of(alias)
        if version_number is None:
            return None
        for raw in self._load()["versions"]:
            if int(raw["version"]) == version_number:
                return self.path.parent / str(raw["checkpoint"])
        return None

    def set_alias(self, alias: str, version: int) -> None:
        payload = self._load()
        versions = {int(item["version"]) for item in payload["versions"]}
        if version not in versions:
            raise KeyError(f"unknown model version: {version}")
        payload["aliases"][alias] = version
        self._save(payload)

    def promote(self, version: int, alias: str = "champion") -> ModelVersion:
        payload = self._load()
        entry = next(
            (
                ModelVersion.from_dict(raw)
                for raw in payload["versions"]
                if int(raw["version"]) == version
            ),
            None,
        )
        if entry is None:
            raise KeyError(f"unknown model version: {version}")
        payload["aliases"][alias] = version
        self._save(payload)
        return entry
