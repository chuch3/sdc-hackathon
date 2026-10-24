from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import torch
from torch import nn

from ..contracts import CalendarOverride, Product
from .config import ModelConfig
from .features import FeatureEncoder, ProductHistory

MODEL_VERSION = "mlp-quantile-1.0.0"


class DemandNet(nn.Module):
    def __init__(
        self,
        num_skus: int,
        num_categories: int,
        numeric_dim: int,
        quantiles: Sequence[float] = (0.1, 0.5, 0.9),
        embedding_dim: int = 8,
        hidden_sizes: Sequence[int] = (64, 32),
        dropout: float = 0.1,
    ) -> None:
        super().__init__()
        if len(quantiles) < 2:
            raise ValueError("at least two quantiles are required")
        if tuple(sorted(quantiles)) != tuple(quantiles):
            raise ValueError("quantiles must be sorted ascending")
        self.quantiles = tuple(float(value) for value in quantiles)
        self.sku_embedding = nn.Embedding(
            num_skus,
            embedding_dim,
            padding_idx=0,
        )
        self.category_embedding = nn.Embedding(
            num_categories,
            embedding_dim,
            padding_idx=0,
        )
        layers: list[nn.Module] = []
        input_dim = numeric_dim + 2 * embedding_dim
        for hidden in hidden_sizes:
            layers.append(nn.Linear(input_dim, hidden))
            layers.append(nn.ReLU())
            if dropout > 0:
                layers.append(nn.Dropout(dropout))
            input_dim = hidden
        layers.append(nn.Linear(input_dim, len(self.quantiles)))
        self.mlp = nn.Sequential(*layers)

    def forward(
        self,
        sku_index: torch.Tensor,
        category_index: torch.Tensor,
        numeric: torch.Tensor,
    ) -> torch.Tensor:
        embedded = torch.cat(
            [
                self.sku_embedding(sku_index),
                self.category_embedding(category_index),
                numeric,
            ],
            dim=1,
        )
        return self.mlp(embedded)


def pinball_loss(
    predictions: torch.Tensor,
    targets: torch.Tensor,
    quantiles: Sequence[float],
) -> torch.Tensor:
    if predictions.shape[1] != len(quantiles):
        raise ValueError("prediction and quantile counts differ")
    target = targets.reshape(-1, 1)
    error = target - predictions
    losses = []
    for index, quantile in enumerate(quantiles):
        column = error[:, index]
        losses.append(
            torch.maximum(quantile * column, (quantile - 1.0) * column)
        )
    return torch.stack(losses, dim=1).mean()


def build_model(
    num_skus: int,
    num_categories: int,
    numeric_dim: int,
    config: ModelConfig,
) -> DemandNet:
    return DemandNet(
        num_skus=num_skus,
        num_categories=num_categories,
        numeric_dim=numeric_dim,
        quantiles=config.quantiles,
        embedding_dim=config.embedding_dim,
        hidden_sizes=config.hidden_sizes,
        dropout=config.dropout,
    )


@dataclass(frozen=True)
class Checkpoint:
    path: Path
    model: DemandNet
    encoder: FeatureEncoder
    model_config: ModelConfig
    metrics: Mapping[str, float]
    trained_at: str
    model_version: str


def save_checkpoint(
    path: Path,
    model: DemandNet,
    encoder: FeatureEncoder,
    config: ModelConfig,
    metrics: Mapping[str, float],
    model_version: str = MODEL_VERSION,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "state_dict": model.state_dict(),
        "encoder": encoder.to_dict(),
        "model_config": {
            "quantiles": list(config.quantiles),
            "embedding_dim": config.embedding_dim,
            "hidden_sizes": list(config.hidden_sizes),
            "dropout": config.dropout,
        },
        "metrics": dict(metrics),
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "model_version": model_version,
    }
    torch.save(payload, path)


def load_checkpoint(path: str | Path, device: str = "cpu") -> Checkpoint:
    checkpoint_path = Path(path)
    if not checkpoint_path.exists():
        raise FileNotFoundError(f"checkpoint not found: {checkpoint_path}")
    payload = torch.load(checkpoint_path, map_location=device, weights_only=True)
    raw_config = payload.get("model_config", {})
    config = ModelConfig(
        quantiles=tuple(float(value) for value in raw_config.get("quantiles", (0.1, 0.5, 0.9))),
        embedding_dim=int(raw_config.get("embedding_dim", 8)),
        hidden_sizes=tuple(int(value) for value in raw_config.get("hidden_sizes", (64, 32))),
        dropout=float(raw_config.get("dropout", 0.1)),
    )
    encoder = FeatureEncoder.from_dict(payload["encoder"])
    model = build_model(
        num_skus=encoder.vocabulary.num_skus,
        num_categories=encoder.vocabulary.num_categories,
        numeric_dim=len(encoder.mean),
        config=config,
    )
    model.load_state_dict(payload["state_dict"])
    model.to(device)
    model.eval()
    return Checkpoint(
        path=checkpoint_path,
        model=model,
        encoder=encoder,
        model_config=config,
        metrics={key: float(value) for key, value in payload.get("metrics", {}).items()},
        trained_at=str(payload.get("trained_at", "")),
        model_version=str(payload.get("model_version", MODEL_VERSION)),
    )


def predict_dates(
    checkpoint: Checkpoint,
    product: Product,
    history: ProductHistory,
    anchor_date: date,
    target_dates: Sequence[date],
    overrides: Sequence[CalendarOverride] = (),
    device: str = "cpu",
) -> list[tuple[float, ...]]:
    if not target_dates:
        return []
    encoded = [
        checkpoint.encoder.encode(
            product,
            history,
            target_date,
            anchor_date,
            overrides,
        )
        for target_date in target_dates
    ]
    sku_tensor = torch.tensor(
        [item[0] for item in encoded],
        dtype=torch.long,
        device=device,
    )
    category_tensor = torch.tensor(
        [item[1] for item in encoded],
        dtype=torch.long,
        device=device,
    )
    numeric_tensor = torch.tensor(
        [item[2] for item in encoded],
        dtype=torch.float32,
        device=device,
    )
    with torch.no_grad():
        predictions = checkpoint.model(
            sku_tensor,
            category_tensor,
            numeric_tensor,
        )
    return [
        tuple(sorted(max(0.0, float(value)) for value in row))
        for row in predictions.cpu().tolist()
    ]
