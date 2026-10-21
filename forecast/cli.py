from __future__ import annotations

import argparse
import json
from datetime import date, timedelta

from .io import load_repository
from .metrics import backtest_forecaster
from .pipeline import ForecastPipeline
from .repository import InMemoryRepository
from .serialization import to_jsonable
from .synthetic import generate_synthetic_dataset


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _format_metric(value: float | None, percent: bool) -> str:
    if value is None:
        return "n/a"
    if percent:
        return f"{value * 100:.1f}%"
    return f"{value:.2f}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Demand forecast and stock recommendation scaffold"
    )
    parser.add_argument("--input", help="JSON file with products, sales, inventory")
    parser.add_argument("--as-of", dest="as_of", help="Business date, YYYY-MM-DD")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--days", type=int, default=56)
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    parser.add_argument("--backtest", action="store_true")
    parser.add_argument("--backtest-horizon", type=int, default=7)
    parser.add_argument("--sku", action="append", help="Limit to a product SKU")
    parser.add_argument(
        "--forecaster",
        choices=["baseline", "ml"],
        default="baseline",
        help="Forecast engine (default: baseline)",
    )
    parser.add_argument("--model-path", help="ML checkpoint path")
    parser.add_argument("--ml-config", help="ML YAML config path")
    args = parser.parse_args(argv)

    as_of = _parse_date(args.as_of) if args.as_of else date.today()
    if args.input:
        repository = load_repository(args.input)
    else:
        dataset = generate_synthetic_dataset(
            seed=args.seed,
            as_of_date=as_of,
            days=args.days,
        )
        repository = InMemoryRepository.from_synthetic(dataset)

    if args.forecaster == "ml":
        from .ml import MLForecaster, load_config

        config = load_config(args.ml_config)
        forecaster = MLForecaster.from_config(
            config,
            checkpoint_path=args.model_path,
        )
        pipeline = ForecastPipeline(repository=repository, forecaster=forecaster)
    else:
        pipeline = ForecastPipeline(repository=repository)
    recommendations = pipeline.recommend_all(as_of, args.sku)

    if args.json:
        payload = {
            "as_of": as_of.isoformat(),
            "recommendations": to_jsonable(recommendations),
        }
        if args.backtest:
            cutoff = as_of - timedelta(days=args.backtest_horizon)
            context = pipeline.build_context(None)
            payload["backtest"] = to_jsonable(
                backtest_forecaster(
                    pipeline.forecaster,
                    context,
                    cutoff,
                    args.backtest_horizon,
                )
            )
        print(json.dumps(payload, indent=2))
        return 0

    print(f"As of {as_of.isoformat()}")
    print()
    for recommendation in recommendations:
        print(
            f"{recommendation.product_name} ({recommendation.product_sku}): "
            f"{recommendation.action.value} {recommendation.quantity:.0f}"
        )
        print(
            f"  confidence={recommendation.confidence.value}, "
            f"expiry_risk={recommendation.expiry_risk}, "
            f"horizon={recommendation.forecast_horizon_days}d"
        )
        for line in recommendation.rationale.splitlines():
            print(f"  {line}")
        print("  why: " + " ".join(recommendation.why))
        print()

    if args.backtest:
        cutoff = as_of - timedelta(days=args.backtest_horizon)
        context = pipeline.build_context(None)
        report = backtest_forecaster(
            pipeline.forecaster,
            context,
            cutoff,
            args.backtest_horizon,
        )
        print(f"Backtest at {cutoff.isoformat()} over {args.backtest_horizon} days")
        for sku, metrics in report.items():
            parts = [
                f"MAE={_format_metric(metrics['MAE'].value, False)}",
                f"MAPE={_format_metric(metrics['MAPE'].value, True)}",
                f"bias={_format_metric(metrics['bias'].value, False)}",
                f"WAPE={_format_metric(metrics['WAPE'].value, True)}",
            ]
            print(f"  {sku}: " + ", ".join(parts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
