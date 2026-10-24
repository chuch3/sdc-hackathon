from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Sequence

import torch

from ..contracts import ForecastContext
from ..metrics import evaluate_metrics
from ..policies import policies_for
from .dataset import TrainingExample
from .features import build_product_history
from .model import Checkpoint, pinball_loss


@dataclass(frozen=True)
class EvaluationReport:
    pinball: float
    coverage: float
    mae: float
    wape: float
    bias: float
    mean_actual: float
    n: int

    def to_dict(self) -> dict[str, float]:
        return {
            "pinball": self.pinball,
            "coverage": self.coverage,
            "MAE": self.mae,
            "WAPE": self.wape,
            "bias": self.bias,
            "mean_actual": self.mean_actual,
            "n": float(self.n),
        }


@dataclass(frozen=True)
class PromotionDecision:
    promote: bool
    reasons: tuple[str, ...]
    candidate: EvaluationReport
    baseline: EvaluationReport


def predict_examples(
    checkpoint: Checkpoint,
    examples: Sequence[TrainingExample],
    batch_size: int = 2048,
) -> list[tuple[float, ...]]:
    predictions: list[tuple[float, ...]] = []
    for start in range(0, len(examples), batch_size):
        batch = examples[start : start + batch_size]
        sku = torch.tensor(
            [item.sku_index for item in batch],
            dtype=torch.long,
        )
        category = torch.tensor(
            [item.category_index for item in batch],
            dtype=torch.long,
        )
        numeric = torch.tensor(
            [list(item.features) for item in batch],
            dtype=torch.float32,
        )
        with torch.no_grad():
            output = checkpoint.model(sku, category, numeric)
        predictions.extend(
            tuple(sorted(max(0.0, float(value)) for value in row))
            for row in output.tolist()
        )
    return predictions


def evaluate_predictions(
    predictions: Sequence[Sequence[float]],
    targets: Sequence[float],
    quantiles: Sequence[float] = (0.1, 0.5, 0.9),
) -> EvaluationReport:
    if len(predictions) != len(targets):
        raise ValueError("predictions and targets must have the same length")
    if not predictions:
        return EvaluationReport(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0)
    prediction_tensor = torch.tensor(
        [list(row) for row in predictions],
        dtype=torch.float32,
    )
    target_tensor = torch.tensor(list(targets), dtype=torch.float32)
    pinball = float(
        pinball_loss(prediction_tensor, target_tensor, quantiles).item()
    )
    lower = prediction_tensor[:, 0]
    upper = prediction_tensor[:, -1]
    covered = (target_tensor >= lower) & (target_tensor <= upper)
    coverage = float(covered.float().mean().item())
    middle = len(quantiles) // 2
    medians = prediction_tensor[:, middle]
    metrics = evaluate_metrics(
        list(targets),
        [float(value) for value in medians.tolist()],
    )
    mean_actual = sum(targets) / len(targets)
    return EvaluationReport(
        pinball=pinball,
        coverage=coverage,
        mae=metrics["MAE"].value or 0.0,
        wape=metrics["WAPE"].value or 0.0,
        bias=metrics["bias"].value or 0.0,
        mean_actual=mean_actual,
        n=len(targets),
    )


def baseline_predictions(
    context: ForecastContext,
    examples: Sequence[TrainingExample],
    min_valid_days: int = 14,
    window_days: int = 28,
) -> list[float]:
    histories = {
        sku: build_product_history(context, sku)
        for sku in {item.product_sku for item in examples}
    }
    predictions: list[float] = []
    for example in examples:
        product = context.products[example.product_sku]
        history = histories[product.sku]
        anchor = example.target_date - timedelta(days=1)
        values = history.window_values(anchor, window_days)
        base_mean = (
            sum(values) / len(values)
            if len(values) >= min_valid_days
            else 0.0
        )
        if base_mean <= 0:
            predictions.append(0.0)
            continue
        policy = policies_for(product).demand
        factor = policy.weekday_factor(product, example.target_date)
        factor *= policy.seasonal_factor(
            product,
            example.target_date,
            context.overrides,
        )
        predictions.append(base_mean * factor)
    return predictions


def report_from_point_predictions(
    predictions: Sequence[float],
    targets: Sequence[float],
) -> EvaluationReport:
    metrics = evaluate_metrics(list(targets), list(predictions))
    mean_actual = sum(targets) / len(targets) if targets else 0.0
    return EvaluationReport(
        pinball=0.0,
        coverage=0.0,
        mae=metrics["MAE"].value or 0.0,
        wape=metrics["WAPE"].value or 0.0,
        bias=metrics["bias"].value or 0.0,
        mean_actual=mean_actual,
        n=len(targets),
    )


def evaluate_checkpoint(
    checkpoint: Checkpoint,
    examples: Sequence[TrainingExample],
) -> EvaluationReport:
    predictions = predict_examples(checkpoint, examples)
    targets = [item.target for item in examples]
    return evaluate_predictions(
        predictions,
        targets,
        checkpoint.model.quantiles,
    )


def promotion_gate(
    candidate: EvaluationReport,
    baseline: EvaluationReport,
    coverage_target: float = 0.80,
    coverage_tolerance: float = 0.08,
    bias_tolerance: float = 0.10,
    max_wape_regression: float = 0.01,
) -> PromotionDecision:
    reasons: list[str] = []
    if candidate.wape > baseline.wape + max_wape_regression:
        reasons.append(
            f"WAPE {candidate.wape:.3f} regressed from baseline "
            f"{baseline.wape:.3f} by more than {max_wape_regression:.1%}"
        )
    if candidate.mean_actual > 0:
        bias_ratio = abs(candidate.bias) / candidate.mean_actual
        if bias_ratio > bias_tolerance:
            reasons.append(
                f"bias {bias_ratio:.1%} exceeds {bias_tolerance:.0%} tolerance"
            )
    if abs(candidate.coverage - coverage_target) > coverage_tolerance:
        reasons.append(
            f"80% interval coverage {candidate.coverage:.1%} is outside "
            f"{coverage_target - coverage_tolerance:.0%}"
            f"-{coverage_target + coverage_tolerance:.0%}"
        )
    return PromotionDecision(
        promote=not reasons,
        reasons=tuple(reasons),
        candidate=candidate,
        baseline=baseline,
    )
