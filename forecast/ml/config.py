from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).with_name("config.yaml")


@dataclass(frozen=True)
class ModelConfig:
    quantiles: tuple[float, ...] = (0.1, 0.5, 0.9)
    embedding_dim: int = 8
    hidden_sizes: tuple[int, ...] = (64, 32)
    dropout: float = 0.1


@dataclass(frozen=True)
class TrainConfig:
    days: int = 730
    products: int = 60
    epochs: int = 40
    batch_size: int = 256
    learning_rate: float = 0.001
    weight_decay: float = 0.00001
    validation_fraction: float = 0.2
    seed: int = 42
    min_history_days: int = 28


@dataclass(frozen=True)
class MLflowConfig:
    enabled: bool = True
    tracking_uri: str | None = None
    registry_uri: str | None = None
    experiment: str = "inventory-demand"
    model_name: str = "demand_forecaster"
    alias: str = "champion"
    challenger_alias: str = "challenger"


@dataclass(frozen=True)
class MLConfig:
    model: ModelConfig = field(default_factory=ModelConfig)
    train: TrainConfig = field(default_factory=TrainConfig)
    mlflow: MLflowConfig = field(default_factory=MLflowConfig)
    artifact_dir: Path = Path("forecast/artifacts")
    checkpoint_name: str = "model.pt"

    @property
    def checkpoint_path(self) -> Path:
        return self.artifact_dir / self.checkpoint_name

    @property
    def registry_path(self) -> Path:
        return self.artifact_dir / "registry.json"


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_str(name: str, default: str | None) -> str | None:
    raw = os.environ.get(name)
    return raw if raw else default


def _tuple(value: Any, cast: type) -> tuple:
    if value is None:
        return ()
    return tuple(cast(item) for item in value)


def load_config(path: str | Path | None = None) -> MLConfig:
    config_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    raw: dict[str, Any] = {}
    if config_path.exists():
        loaded = yaml.safe_load(config_path.read_text()) or {}
        if not isinstance(loaded, dict):
            raise ValueError(f"config must be a mapping: {config_path}")
        raw = loaded

    model_raw = raw.get("model", {}) or {}
    train_raw = raw.get("train", {}) or {}
    mlflow_raw = raw.get("mlflow", {}) or {}

    model = ModelConfig(
        quantiles=_tuple(model_raw.get("quantiles"), float)
        or ModelConfig().quantiles,
        embedding_dim=int(model_raw.get("embedding_dim", 8)),
        hidden_sizes=_tuple(model_raw.get("hidden_sizes"), int) or (64, 32),
        dropout=float(model_raw.get("dropout", 0.1)),
    )
    train = TrainConfig(
        days=int(train_raw.get("days", 730)),
        products=int(train_raw.get("products", 60)),
        epochs=int(train_raw.get("epochs", 40)),
        batch_size=int(train_raw.get("batch_size", 256)),
        learning_rate=float(train_raw.get("learning_rate", 0.001)),
        weight_decay=float(train_raw.get("weight_decay", 0.00001)),
        validation_fraction=float(train_raw.get("validation_fraction", 0.2)),
        seed=int(train_raw.get("seed", 42)),
        min_history_days=int(train_raw.get("min_history_days", 28)),
    )
    artifact_dir_raw = _env_str(
        "FORECAST_ML_ARTIFACT_DIR",
        raw.get("artifact_dir", "forecast/artifacts"),
    )
    artifact_dir = Path(artifact_dir_raw or "forecast/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    tracking_uri = _env_str(
        "MLFLOW_TRACKING_URI",
        mlflow_raw.get("tracking_uri"),
    ) or f"sqlite:///{(artifact_dir / 'mlflow.db').resolve()}"
    registry_uri = _env_str(
        "MLFLOW_REGISTRY_URI",
        mlflow_raw.get("registry_uri"),
    ) or tracking_uri
    mlflow = MLflowConfig(
        enabled=_env_bool("MLFLOW_ENABLED", bool(mlflow_raw.get("enabled", True))),
        tracking_uri=tracking_uri,
        registry_uri=registry_uri,
        experiment=_env_str(
            "MLFLOW_EXPERIMENT_NAME",
            mlflow_raw.get("experiment", "inventory-demand"),
        )
        or "inventory-demand",
        model_name=_env_str(
            "MLFLOW_MODEL_NAME",
            mlflow_raw.get("model_name", "demand_forecaster"),
        )
        or "demand_forecaster",
        alias=_env_str(
            "MLFLOW_MODEL_ALIAS",
            mlflow_raw.get("alias", "champion"),
        )
        or "champion",
        challenger_alias=_env_str(
            "MLFLOW_CHALLENGER_ALIAS",
            mlflow_raw.get("challenger_alias", "challenger"),
        )
        or "challenger",
    )
    return MLConfig(
        model=model,
        train=train,
        mlflow=mlflow,
        artifact_dir=artifact_dir,
        checkpoint_name=str(raw.get("checkpoint_name", "model.pt")),
    )
