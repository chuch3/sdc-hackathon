from datetime import date
from typing import Any, Dict
from app.domains.base import DemandPolicy, PlanningPolicy, AdvicePolicy


class BakeryPolicy(DemandPolicy, PlanningPolicy, AdvicePolicy):
    """Bakery domain implementation covering bake plans, dayparts, and seasonal advice."""

    # Default daypart split shares across operating hours
    DEFAULT_DAYPART_SHARES = {
        "morning": 0.55,
        "midday": 0.30,
        "afternoon": 0.15,
    }

    # Weekend demand boost factor
    WEEKEND_FACTOR = 1.18

    # 1. Demand Adjustment Logic
    def calculate_adjusted_demand(self, base_demand: float, target_date: date, **kwargs) -> float:
        """Adjusts baseline demand using weekday/weekend patterns."""
        # Check if the target day is Saturday (5) or Sunday (6)
        is_weekend = target_date.weekday() >= 5
        multiplier = self.WEEKEND_FACTOR if is_weekend else 1.0

        # Apply any custom event or holiday multiplier passed via kwargs
        holiday_factor = kwargs.get("holiday_factor", 1.0)
        return round(base_demand * multiplier * holiday_factor, 2)

    # 2. Daily Bake Planning Logic
    def generate_plan(self, forecast: float, current_stock: float, **kwargs) -> Dict[str, Any]:
        """Calculates total bake quantity and distributes across dayparts."""
        buffer_percent = kwargs.get("buffer_percent", 0.06)  # Default 6% buffer
        safe_carryover = kwargs.get("safe_carryover", 0.0)

        # Planned quantity: (forecast * buffer) - safe carryover stock
        gross_needed = forecast * (1.0 + buffer_percent)
        net_bake_qty = max(0, int(round(gross_needed - safe_carryover)))

        # Split total bake into dayparts
        daypart_splits = {}
        for daypart, share in self.DEFAULT_DAYPART_SHARES.items():
            daypart_splits[daypart] = int(round(net_bake_qty * share))

        # Adjust minor rounding difference into the morning batch
        allocated_total = sum(daypart_splits.values())
        diff = net_bake_qty - allocated_total
        daypart_splits["morning"] += diff

        return {
            "total_bake_quantity": net_bake_qty,
            "daypart_breakdown": daypart_splits,
            "buffer_used": f"{int(buffer_percent * 100)}%",
            "safe_carryover_deducted": safe_carryover,
            "action": "BAKE",
        }

    # 3. Seasonal & Markdown Advice Logic
    def get_recommendation(self, product_id: str, stock_data: Any, **kwargs) -> Dict[str, Any]:
        """Provides markdown window guidance, donation actions, or seasonal advice."""
        current_hour = kwargs.get("current_hour", 12)
        seasonal_ingredient = kwargs.get("seasonal_ingredient", None)

        advice_notes = []

        # Markdown policy after standard evening window (e.g., after 17:30 / 5 PM)
        if current_hour >= 17:
            markdown_rate = kwargs.get("markdown_discount", "30%")
            advice_notes.append(f"Markdown window active: discount {markdown_rate} before close.")

        # Seasonal bread suggestion if seasonal ingredient is in stock/season
        if seasonal_ingredient:
            advice_notes.append(f"{seasonal_ingredient} is in season; consider feature batch.")

        return {
            "product_id": product_id,
            "advice": advice_notes or ["Standard display and shelf tracking."],
            "markdown_window_open": current_hour >= 17,
            "action": "MARKDOWN" if current_hour >= 17 else "HOLD",
        }
