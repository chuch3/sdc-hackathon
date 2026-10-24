from __future__ import annotations

import argparse
import copy
import os
from dataclasses import replace
from datetime import date
from typing import Sequence

import torch

from ..contracts import ForecastContext
from ..repository import InMemoryRepository
from .catalog import build_training_dataset
from .config import load_config
from .dataset import TrainingExample, build_training_examples, split_examples
from .evaluate import (
    EvaluationReport,
    baseline_predictions,
    evaluate_checkpoint,
    promotion_gate,
    report_from_point_predictions,
)
from .features import (
    NUMERIC_FEATURE_DIM,
    FeatureEncoder,
    FeatureVocabulary,
)
from .mlflow_client import build_tracker
from .model import build_model, load_checkpoint, pinball_loss, save_checkpoint
from .registry import LocalModelRegistry


def _normalize(
    examples: Sequence[TrainingExample],
    encoder: FeatureEncoder,
) -> list[TrainingExample]:
    normalized: list[TrainingExample] = []
    for example in examples:
        features = tuple(
            (value - mean) / std
            for value, mean, std in zip(
                example.features,
                encoder.mean,
                encoder.std,
            )
        )
        normalized.append(replace(example, features=features))
    return normalized


def _tensors(examples: Sequence[TrainingExample]):
    return (
        torch.tensor(
            [item.sku_index for item in examples],
            dtype=torch.long,
        ),
        torch.tensor(
            [item.category_index for item in examples],
            dtype=torch.long,
        ),
        torch.tensor(
            [list(item.features) for item in examples],
            dtype=torch.float32,
        ),
        torch.tensor(
            [item.target for item in examples],
            dtype=torch.float32,
        ),
    )


def _validation_loss(
    model: torch.nn.Module,
    tensors,
    quantiles: Sequence[float],
    batch_size: int,
) -> float:
    sku, category, numeric, target = tensors
    total = 0.0
    count = 0
    model.eval()
    with torch.no_grad():
        for start in range(0, len(sku), batch_size):
            end = start + batch_size
            predictions = model(
                sku[start:end],
                category[start:end],
                numeric[start:end],
            )
            loss = pinball_loss(
                predictions,
                target[start:end],
                quantiles,
            )
            total += float(loss.item()) * (end - start)
            count += end - start
    return total / max(count, 1)


def _run_training(
    model: torch.nn.Module,
    train_tensors,
    validation_tensors,
    quantiles: Sequence[float],
    epochs: int,
    batch_size: int,
    learning_rate: float,
    weight_decay: float,
) -> tuple[dict, dict]:
    optimizer = torch.optim.Adam(
        model.parameters(),
        lr=learning_rate,
        weight_decay=weight_decay,
    )
    best_state = copy.deepcopy(model.state_dict())
    best_loss = float("inf")
    patience = 5
    stale_epochs = 0
    history: list[dict[str, float]] = []
    sku, category, numeric, target = train_tensors
    count = len(sku)
    for epoch in range(1, epochs + 1):
        model.train()
        permutation = torch.randperm(count)
        total = 0.0
        for start in range(0, count, batch_size):
            indices = permutation[start : start + batch_size]
            optimizer.zero_grad()
            predictions = model(
                sku[indices],
                category[indices],
                numeric[indices],
            )
            loss = pinball_loss(predictions, target[indices], quantiles)
            loss.backward()
            optimizer.step()
            total += float(loss.item()) * len(indices)
        train_loss = total / max(count, 1)
        validation_loss = _validation_loss(
            model,
            validation_tensors,
            quantiles,
            batch_size,
        )
        history.append(
            {
                "epoch": float(epoch),
                "train_pinball": train_loss,
                "validation_pinball": validation_loss,
            }
        )
        if validation_loss < best_loss - 1e-5:
            best_loss = validation_loss
            best_state = copy.deepcopy(model.state_dict())
            stale_epochs = 0
        else:
            stale_epochs += 1
            if stale_epochs >= patience:
                break
    model.load_state_dict(best_state)
    return best_state, {
        "best_validation_pinball": best_loss,
        "epochs_run": float(len(history)),
    }


def _format_report(name: str, report: EvaluationReport) -> str:
    return (
        f"{name}: pinball={report.pinball:.3f}, coverage={report.coverage:.1%}, "
        f"MAE={report.mae:.2f}, WAPE={report.wape:.1%}, "
        f"bias={report.bias:.2f}, n={report.n}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Train the quantile demand model",
    )
    parser.add_argument("--config", help="YAML config path")
    parser.add_argument("--checkpoint", help="Checkpoint output path")
    parser.add_argument("--as-of", dest="as_of", help="Business date, YYYY-MM-DD")
    parser.add_argument("--days", type=int, help="Synthetic history length")
    parser.add_argument("--products", type=int, help="Number of synthetic SKUs")
    parser.add_argument("--epochs", type=int, help="Training epochs")
    parser.add_argument("--seed", type=int, help="Random seed")
    parser.add_argument("--no-mlflow", action="store_true")
    parser.add_argument("--no-register", action="store_true")
    parser.add_argument("--no-promote", action="store_true")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    train_config = config.train
    if args.days or args.products or args.epochs or args.seed is not None:
        train_config = replace(
            train_config,
            days=args.days or train_config.days,
            products=args.products or train_config.products,
            epochs=args.epochs or train_config.epochs,
            seed=args.seed if args.seed is not None else train_config.seed,
        )
    config = replace(config, train=train_config)

    torch.manual_seed(train_config.seed)
    torch.set_num_threads(max(1, min(4, os.cpu_count() or 1)))
    as_of = date.fromisoformat(args.as_of) if args.as_of else None

    dataset = build_training_dataset(
        seed=train_config.seed,
        as_of_date=as_of,
        days=train_config.days,
        products=train_config.products,
    )
    repository = InMemoryRepository.from_synthetic(dataset)
    context = ForecastContext(
        products={product.sku: product for product in repository.products()},
        sales_history=tuple(repository.sales_history()),
        overrides=tuple(repository.overrides()),
    )

    vocabulary = FeatureVocabulary.from_products(context.products.values())
    identity = FeatureEncoder(
        vocabulary=vocabulary,
        mean=tuple(0.0 for _ in range(NUMERIC_FEATURE_DIM)),
        std=tuple(1.0 for _ in range(NUMERIC_FEATURE_DIM)),
    )
    raw_examples = build_training_examples(
        context,
        identity,
        min_history_days=train_config.min_history_days,
    )
    if len(raw_examples) < 50:
        raise RuntimeError(
            "not enough training examples; increase --days or --products"
        )
    train_raw, validation_raw = split_examples(
        raw_examples,
        train_config.validation_fraction,
    )
    encoder = FeatureEncoder.fit(
        vocabulary,
        [list(item.features) for item in train_raw],
    )
    train_examples = _normalize(train_raw, encoder)
    validation_examples = _normalize(validation_raw, encoder)

    model = build_model(
        num_skus=vocabulary.num_skus,
        num_categories=vocabulary.num_categories,
        numeric_dim=len(encoder.mean),
        config=config.model,
    )
    train_tensors = _tensors(train_examples)
    validation_tensors = _tensors(validation_examples)
    _, training_metrics = _run_training(
        model,
        train_tensors,
        validation_tensors,
        config.model.quantiles,
        train_config.epochs,
        train_config.batch_size,
        train_config.learning_rate,
        train_config.weight_decay,
    )
    print(
        f"Trained {int(training_metrics['epochs_run'])} epoch(s); "
        f"best validation pinball "
        f"{training_metrics['best_validation_pinball']:.3f}."
    )

    checkpoint_path = (
        args.checkpoint if args.checkpoint else config.checkpoint_path
    )
    save_checkpoint(
        checkpoint_path,
        model,
        encoder,
        config.model,
        training_metrics,
    )
    checkpoint = load_checkpoint(checkpoint_path)
    candidate = evaluate_checkpoint(checkpoint, validation_examples)
    baseline = report_from_point_predictions(
        baseline_predictions(context, validation_examples),
        [item.target for item in validation_examples],
    )
    decision = promotion_gate(candidate, baseline)

    print(_format_report("ML", candidate))
    print(_format_report("Baseline", baseline))
    if decision.promote:
        print("Promotion gate passed.")
    else:
        print("Promotion gate failed:")
        for reason in decision.reasons:
            print(f"  - {reason}")

    if not args.no_register:
        registry = LocalModelRegistry(
            config.registry_path,
            model_name=config.mlflow.model_name,
        )
        version = registry.register(
            checkpoint_path,
            candidate.to_dict(),
            alias=config.mlflow.challenger_alias,
        )
        if decision.promote and not args.no_promote:
            registry.promote(version.version, config.mlflow.alias)
            print(
                f"Registered version {version.version} as "
                f"{config.mlflow.alias}."
            )
        else:
            print(
                f"Registered version {version.version} as "
                f"{config.mlflow.challenger_alias}."
            )

    if not args.no_mlflow and config.mlflow.enabled:
        tracker = build_tracker(config.mlflow, config.artifact_dir)
        if tracker.enabled:
            try:
                tracker.start_run(run_name="mlp-quantile-train")
                tracker.log_params(
                    {
                        "model": {
                            "quantiles": list(config.model.quantiles),
                            "embedding_dim": config.model.embedding_dim,
                            "hidden_sizes": list(config.model.hidden_sizes),
                        },
                        "train": {
                            "days": train_config.days,
                            "products": train_config.products,
                            "epochs": train_config.epochs,
                            "batch_size": train_config.batch_size,
                            "learning_rate": train_config.learning_rate,
                            "seed": train_config.seed,
                        },
                    }
                )
                tracker.log_metrics(
                    {
                        f"ml_{key}": value
                        for key, value in candidate.to_dict().items()
                    }
                    | {
                        f"baseline_{key}": value
                        for key, value in baseline.to_dict().items()
                    }
                    | {
                        "promote": 1.0 if decision.promote else 0.0,
                        **training_metrics,
                    }
                )
                tracker.log_artifact(checkpoint_path)
                tracker.log_dict(
                    {
                        "candidate": candidate.to_dict(),
                        "baseline": baseline.to_dict(),
                        "promotion": {
                            "promote": decision.promote,
                            "reasons": list(decision.reasons),
                        },
                    },
                    "evaluation.json",
                )
            finally:
                tracker.end_run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
