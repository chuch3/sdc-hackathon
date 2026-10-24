from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Any, Mapping, Protocol

from .config import MLflowConfig


class Tracker(Protocol):
    enabled: bool

    def start_run(self, run_name: str | None = None) -> str: ...

    def log_params(self, params: Mapping[str, Any]) -> None: ...

    def log_metrics(self, metrics: Mapping[str, float]) -> None: ...

    def log_artifact(self, path: str | Path) -> None: ...

    def log_dict(self, payload: Mapping[str, Any], name: str) -> None: ...

    def end_run(self) -> None: ...


class NullTracker:
    enabled = False

    def start_run(self, run_name: str | None = None) -> str:
        return ""

    def log_params(self, params: Mapping[str, Any]) -> None:
        return None

    def log_metrics(self, metrics: Mapping[str, float]) -> None:
        return None

    def log_artifact(self, path: str | Path) -> None:
        return None

    def log_dict(self, payload: Mapping[str, Any], name: str) -> None:
        return None

    def end_run(self) -> None:
        return None


def _flat_params(values: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, value in values.items():
        name = f"{prefix}{key}"
        if isinstance(value, Mapping):
            flat.update(_flat_params(value, prefix=f"{name}."))
        elif isinstance(value, (list, tuple)):
            flat[name] = json.dumps(list(value))
        elif value is not None:
            flat[name] = value
    return flat


class MlflowTracker:
    enabled = True

    def __init__(
        self,
        config: MLflowConfig,
        artifact_dir: Path | None = None,
    ) -> None:
        import mlflow

        self._mlflow = mlflow
        self._config = config
        if config.tracking_uri:
            mlflow.set_tracking_uri(config.tracking_uri)
        if config.registry_uri:
            mlflow.set_registry_uri(config.registry_uri)
        experiment = mlflow.get_experiment_by_name(config.experiment)
        if experiment is None and artifact_dir is not None:
            artifact_location = (
                Path(artifact_dir) / "mlruns"
            ).resolve().as_uri()
            mlflow.create_experiment(
                config.experiment,
                artifact_location=artifact_location,
            )
        mlflow.set_experiment(config.experiment)
        self._run = None

    @property
    def run_id(self) -> str:
        if self._run is None:
            return ""
        return self._run.info.run_id

    def start_run(self, run_name: str | None = None) -> str:
        self._run = self._mlflow.start_run(run_name=run_name)
        return self.run_id

    def log_params(self, params: Mapping[str, Any]) -> None:
        self._mlflow.log_params(_flat_params(params))

    def log_metrics(self, metrics: Mapping[str, float]) -> None:
        self._mlflow.log_metrics(
            {key: float(value) for key, value in metrics.items()}
        )

    def log_artifact(self, path: str | Path) -> None:
        self._mlflow.log_artifact(str(path))

    def log_dict(self, payload: Mapping[str, Any], name: str) -> None:
        self._mlflow.log_dict(dict(payload), name)

    def end_run(self) -> None:
        if self._run is not None:
            self._mlflow.end_run()
            self._run = None


def build_tracker(
    config: MLflowConfig,
    artifact_dir: Path | None = None,
) -> Tracker:
    if not config.enabled:
        return NullTracker()
    try:
        return MlflowTracker(config, artifact_dir=artifact_dir)
    except Exception as error:
        warnings.warn(
            f"MLflow tracking disabled: {type(error).__name__}: {error}",
            RuntimeWarning,
            stacklevel=2,
        )
        return NullTracker()
